import json
import pandas as pd
import pytest

from ty_quant_node.core.handles import Handle
from ty_quant_node.core.security import resolve_allowed_path, resolve_node_path
from ty_quant_node.backend.market import export_qlib, check_provider_consistency


def test_handle_roundtrip_and_kind_validation(tmp_path):
    handle = Handle(kind="QLIB_EXPORT", path=str(tmp_path), metadata={"rows": 2})
    restored = Handle.from_dict(json.loads(json.dumps(handle.to_dict())))
    assert restored.kind == "QLIB_EXPORT"
    assert restored.metadata["rows"] == 2
    with pytest.raises(ValueError, match="未知句柄类型"):
        Handle.from_dict({"kind": "UNKNOWN", "version": "1", "path": "x"})


def test_path_must_stay_under_allowed_root(tmp_path):
    assert resolve_allowed_path(tmp_path / "data.csv", [tmp_path]) == (tmp_path / "data.csv").resolve()
    with pytest.raises(ValueError, match="白名单"):
        resolve_allowed_path(tmp_path.parent / "outside.csv", [tmp_path])
    with pytest.raises(ValueError, match="路径穿越"):
        resolve_allowed_path(tmp_path / ".." / "outside.csv", [tmp_path])


def test_node_path_policy_uses_configured_roots_and_rejects_urls(tmp_path, monkeypatch):
    input_path = tmp_path / "input.csv"
    input_path.write_text("instrument,datetime\nAAA,2024-01-01\n", encoding="utf-8")
    monkeypatch.setenv("TY_QUANT_ALLOWED_ROOTS", str(tmp_path))

    assert resolve_node_path(input_path, must_exist=True) == input_path.resolve()
    with pytest.raises(ValueError, match="本地文件路径"):
        resolve_node_path("https://example.com/market.csv")
    with pytest.raises(ValueError, match="白名单"):
        resolve_node_path(tmp_path.parent / "outside.csv")


def test_qlib_export_writes_consistent_provider(tmp_path, market_frame):
    handle = export_qlib(market_frame, tmp_path / "provider", adjustment="qfq")
    provider = tmp_path / "provider"
    assert handle.kind == "QLIB_EXPORT"
    assert (provider / "calendars" / "day.txt").exists()
    assert (provider / "instruments" / "all.txt").exists()
    assert (provider / "features" / "aaa" / "close.day.bin").exists()
    manifest = json.loads((provider / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["adjustment"] == "qfq"
    assert manifest["anchor_factor"] == 2.0
    assert manifest["factor_definition"] == "adjusted/original"
    assert manifest["calendar_count"] == 6
    assert check_provider_consistency(provider)["consistent"] is True


def test_qlib_reads_exported_binary_provider(tmp_path, market_frame):
    pytest.importorskip("qlib")
    export_qlib(market_frame, tmp_path / "provider", adjustment="qfq")
    import qlib
    from qlib.data import D

    qlib.init(provider_uri=str(tmp_path / "provider"), region="cn", dataset_cache=None, expression_cache=None)
    result = D.features(["AAA"], ["$close"], start_time="2024-01-01", end_time="2024-01-06", freq="day", disk_cache=0)
    assert len(result) == 6
    assert result["$close"].notna().all()


def test_provider_consistency_rejects_tampered_manifest_file(tmp_path, market_frame):
    provider = tmp_path / "provider"
    export_qlib(market_frame, provider, adjustment="qfq")
    dataset = provider / "dataset.parquet"
    dataset.write_bytes(dataset.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="hash"):
        check_provider_consistency(provider)


@pytest.fixture
def market_frame():
    rows = []
    for i, dt in enumerate(pd.date_range("2024-01-01", periods=6)):
        for instrument, base in (("AAA", 10 + i), ("BBB", 20 - i * 0.2)):
            rows.append(
                {
                    "datetime": dt,
                    "instrument": instrument,
                    "open_raw": base,
                    "high_raw": base + 1,
                    "low_raw": base - 1,
                    "close_raw": base,
                    "volume_raw": 1000.0,
                    "amount_raw": base * 1000,
                    "adj_factor": 1.0 if i < 3 else 2.0,
                    "trade_status": 1,
                }
            )
    return pd.DataFrame(rows)
