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
