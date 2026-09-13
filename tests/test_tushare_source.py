import pandas as pd
import pytest

from ty_quant_node.data.tushare_source import TushareDailySource, TushareError


def test_tushare_daily_merges_raw_and_adjustment_factor_without_leaking_token():
    calls = []

    def transport(payload):
        calls.append(payload)
        if payload["api_name"] == "daily":
            return {"code": 0, "data": {"fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"], "items": [["000001.SZ", "20240102", 10, 11, 9, 10.5, 100, 1000]]}}
        return {"code": 0, "data": {"fields": ["ts_code", "trade_date", "adj_factor"], "items": [["000001.SZ", "20240102", 2.0]]}}

    source = TushareDailySource(token="secret-token", transport=transport, sleep=lambda _: None)
    result = source.fetch(["000001.SZ"], "20240101", "20240103")
    assert result.loc[0, "instrument"] == "000001.SZ"
    assert result.loc[0, "adj_factor"] == 2.0
    assert result.loc[0, "close_raw"] == 10.5
    assert all("secret-token" not in repr(call) for call in calls)
    assert str(calls[0]["token"]) == "secret-token"
    assert {call["api_name"] for call in calls} == {"daily", "adj_factor"}


def test_tushare_retries_network_failures_without_exposing_token():
    attempts = []

    def transport(_payload):
        attempts.append(1)
        raise OSError("offline")

    with pytest.raises(TushareError, match="网络请求失败"):
        TushareDailySource(token="secret-token", transport=transport, retries=3, sleep=lambda _: None)._call("daily", {})
    assert len(attempts) == 3


def test_tushare_can_attach_normalized_corporate_action_events():
    def transport(payload):
        if payload["api_name"] == "daily":
            return {"code": 0, "data": {"fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"], "items": [["000001.SZ", "20240102", 10, 11, 9, 10.5, 100, 1000]]}}
        if payload["api_name"] == "adj_factor":
            return {"code": 0, "data": {"fields": ["ts_code", "trade_date", "adj_factor"], "items": [["000001.SZ", "20240102", 2.0]]}}
        return {"code": 0, "data": {"fields": ["instrument", "effective_date", "price_multiplier", "split_multiplier", "knowledge_date"], "items": [["000001.SZ", "20240102", 2.0, 2.0, "20240102"]]}}

    source = TushareDailySource(token="secret-token", transport=transport, sleep=lambda _: None)
    result = source.fetch(["000001.SZ"], "20240101", "20240103", include_events=True)
    assert result.attrs["events"][0]["price_multiplier"] == 2.0


def test_tushare_normalizes_dates_and_ignores_volatile_asof_in_snapshot_id():
    calls = []

    def transport(payload):
        calls.append(payload)
        if payload["api_name"] == "daily":
            return {"code": 0, "data": {"fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"], "items": [["000001.SZ", "20240102", 10, 11, 9, 10.5, 100, 1000]]}}
        return {"code": 0, "data": {"fields": ["ts_code", "trade_date", "adj_factor"], "items": [["000001.SZ", "20240102", 2.0]]}}

    source = TushareDailySource(token="secret-token", transport=transport, sleep=lambda _: None)
    first = source.fetch([" 000001.sz "], "2024-01-01", "2024-01-03")
    second = first.copy()
    second["asof"] = "a different pull time"
    assert calls[0]["params"]["ts_code"] == "000001.SZ"
    assert calls[0]["params"]["start_date"] == "20240101"
    assert calls[0]["params"]["end_date"] == "20240103"
    assert source.snapshot_id(first) == source.snapshot_id(second)


def test_tushare_stk_div_uses_per_share_ratio():
    def transport(payload):
        if payload["api_name"] == "daily":
            return {"code": 0, "data": {"fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"], "items": [["000001.SZ", "20240102", 10, 11, 9, 10.5, 100, 1000]]}}
        if payload["api_name"] == "adj_factor":
            return {"code": 0, "data": {"fields": ["ts_code", "trade_date", "adj_factor"], "items": [["000001.SZ", "20240102", 2.0]]}}
        return {"code": 0, "data": {"fields": ["ts_code", "ex_date", "ann_date", "stk_div"], "items": [["000001.SZ", "20240103", "20240101", 0.2]]}}

    source = TushareDailySource(token="secret-token", transport=transport, sleep=lambda _: None)
    result = source.fetch(["000001.SZ"], "20240101", "20240105", include_events=True)
    assert result.attrs["events"][0]["split_multiplier"] == pytest.approx(1.2)


def test_tushare_splits_large_code_and_date_queries():
    calls = []

    def transport(payload):
        calls.append(payload)
        params = payload["params"]
        codes = params["ts_code"].split(",")
        date = params["start_date"]
        if payload["api_name"] == "daily":
            fields = ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"]
            items = [[code, date, 10, 11, 9, 10.5, 100, 1000] for code in codes]
        else:
            fields = ["ts_code", "trade_date", "adj_factor"]
            items = [[code, date, 2.0] for code in codes]
        return {"code": 0, "data": {"fields": fields, "items": items}}

    source = TushareDailySource(
        token="secret-token",
        transport=transport,
        max_codes_per_request=1,
        max_days_per_request=2,
        sleep=lambda _: None,
    )
    result = source.fetch(["000001.SZ", "600000.SH"], "20240101", "20240103")

    assert len(calls) == 8
    assert {call["api_name"] for call in calls} == {"daily", "adj_factor"}
    assert {call["params"]["ts_code"] for call in calls} == {"000001.SZ", "600000.SH"}
    assert {call["params"]["start_date"] for call in calls} == {"20240101", "20240103"}
    assert len(result) == 4
    assert result["adj_factor"].notna().all()


def test_tushare_rejects_missing_adjustment_factor_rows():
    def transport(payload):
        if payload["api_name"] == "daily":
            return {"code": 0, "data": {"fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"], "items": [["000001.SZ", "20240102", 10, 11, 9, 10.5, 100, 1000]]}}
        return {"code": 0, "data": {"fields": ["ts_code", "trade_date", "adj_factor"], "items": []}}

    source = TushareDailySource(token="secret-token", transport=transport, sleep=lambda _: None)

    with pytest.raises(TushareError, match="复权因子缺失"):
        source.fetch(["000001.SZ"], "20240101", "20240103")


def test_tushare_rejects_duplicate_adjustment_factor_keys():
    def transport(payload):
        if payload["api_name"] == "daily":
            return {"code": 0, "data": {"fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"], "items": [["000001.SZ", "20240102", 10, 11, 9, 10.5, 100, 1000]]}}
        return {"code": 0, "data": {"fields": ["ts_code", "trade_date", "adj_factor"], "items": [["000001.SZ", "20240102", 2.0], ["000001.SZ", "20240102", 2.0]]}}

    source = TushareDailySource(token="secret-token", transport=transport, sleep=lambda _: None)

    with pytest.raises(TushareError, match="重复"):
        source.fetch(["000001.SZ"], "20240101", "20240103")


def test_tushare_rejects_malformed_response_payload():
    source = TushareDailySource(token="secret-token", transport=lambda _payload: None, sleep=lambda _: None)

    with pytest.raises(TushareError, match="返回格式无效"):
        source._call("daily", {})
