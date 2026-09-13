import json

import pandas as pd

from ty_quant_node.nodes import TushareConfig, TushareDailyFetch, TushareToQlib


class _FakeSource:
    def __init__(self, **_kwargs):
        pass

    def fetch(self, codes, start, end, *, include_events=False):
        frame = pd.DataFrame([
            {"instrument": codes[0], "datetime": "2024-01-01", "open_raw": 10, "high_raw": 11, "low_raw": 9, "close_raw": 10, "volume_raw": 100, "amount_raw": 1000, "adj_factor": 1.0},
            {"instrument": codes[0], "datetime": "2024-01-02", "open_raw": 5, "high_raw": 6, "low_raw": 4, "close_raw": 5, "volume_raw": 200, "amount_raw": 1000, "adj_factor": 2.0},
        ])
        frame.attrs["events"] = [{"instrument": codes[0], "effective_date": "2024-01-02", "price_multiplier": 2.0, "split_multiplier": 2.0, "knowledge_date": "2024-01-02"}] if include_events else []
        return frame

    @staticmethod
    def snapshot_id(frame, events):
        return "snapshot-test"


def test_tushare_fetch_and_conversion_write_versioned_provider(monkeypatch, tmp_path):
    monkeypatch.setattr("ty_quant_node.nodes.TushareDailySource", _FakeSource)
    config = TushareConfig().run("environment", 3)[0]
    market = TushareDailyFetch().run(config, "000001.SZ", "20240101", "20240102", str(tmp_path / "snapshot"), True)[0]
    assert market["kind"] == "MARKET_DATA"
    assert market["metadata"]["raw_hash"]
    assert market["metadata"]["factor_hash"]
    assert market["metadata"]["events_hash"]
    assert market["metadata"]["files"]["raw"]
    assert market["metadata"]["files"]["events"]
    assert "secret-token" not in json.dumps(market)
    exported = TushareToQlib().run(market, "pit", str(tmp_path / "provider"), True)[0]
    assert exported["kind"] == "QLIB_EXPORT"
    manifest = json.loads((tmp_path / "provider" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["point_in_time"] is True
    assert manifest["snapshot_id"] == "snapshot-test"
    assert manifest["files"]["dataset"]
    assert (tmp_path / "provider" / "features" / "000001.sz" / "ty_close.day.bin").exists()


def test_tushare_config_forwards_environment_name_and_fetch_keeps_old_snapshot(monkeypatch, tmp_path):
    calls = []

    class _VersionedSource(_FakeSource):
        generation = 0

        def __init__(self, **kwargs):
            calls.append(kwargs)

        def fetch(self, codes, start, end, *, include_events=False):
            type(self).generation += 1
            frame = super().fetch(codes, start, end, include_events=include_events).copy()
            frame.loc[0, "close_raw"] += type(self).generation
            return frame

        @staticmethod
        def snapshot_id(frame, events):
            return f"snapshot-{float(frame.iloc[0]['close_raw']):g}"

    monkeypatch.setattr("ty_quant_node.nodes.TushareDailySource", _VersionedSource)
    config = TushareConfig().run("environment", "TY_TOKEN", 3)[0]
    first = TushareDailyFetch().run(config, "000001.SZ", "20240101", "20240102", str(tmp_path / "snapshots"), True)[0]
    second = TushareDailyFetch().run(config, "000001.SZ", "20240101", "20240102", str(tmp_path / "snapshots"), True)[0]
    assert calls == [{"retries": 3, "token_env_name": "TY_TOKEN"}, {"retries": 3, "token_env_name": "TY_TOKEN"}]
    assert first["path"] != second["path"]
    assert (tmp_path / "snapshots" / "manifest.json").exists()
    assert (tmp_path / "snapshots" / "snapshot-12" / "manifest.json").exists()


def test_vendor_factor_fallback_is_marked_non_pit(monkeypatch, tmp_path):
    class _NoEventsSource(_FakeSource):
        def fetch(self, codes, start, end, *, include_events=False):
            frame = super().fetch(codes, start, end, include_events=False)
            frame.attrs["events"] = []
            return frame

    monkeypatch.setattr("ty_quant_node.nodes.TushareDailySource", _NoEventsSource)
    config = TushareConfig().run("environment", "TUSHARE_TOKEN", 3)[0]
    market = TushareDailyFetch().run(config, "000001.SZ", "20240101", "20240102", str(tmp_path / "snapshot"), False)[0]
    exported = TushareToQlib().run(market, "pit", str(tmp_path / "provider"), True)[0]
    assert exported["metadata"]["point_in_time"] is False
    assert exported["metadata"]["adjustment_source"] == "vendor_adj_factor"
