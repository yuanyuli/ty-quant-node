import json
import pytest

from ty_quant_node.core.handles import Handle
from ty_quant_node.nodes import QlibControl, QlibExport, QlibModel


def _control(tmp_path, **overrides):
    values = {
        "csv_path": str(tmp_path / "market.csv"),
        "adjustment": "qfq",
        "output_root": str(tmp_path / "artifacts"),
        "train_start": "2024-01-01",
        "train_end": "2024-01-03",
        "test_start": "2024-01-04",
        "test_end": "2024-01-06",
        "model_type": "linear",
        "params_json": "{}",
        "artifact_dir": str(tmp_path / "model"),
        "segment": "test",
        "topk": 1,
        "n_drop": 0,
        "transaction_cost_bps": 5.0,
        "report_dir": str(tmp_path / "report"),
    }
    values.update(overrides)
    return QlibControl().run(**values)[0]


def test_control_node_returns_versioned_handle(tmp_path):
    control = _control(tmp_path)

    restored = Handle.from_dict(json.loads(json.dumps(control)))

    assert restored.kind == "QLIB_CONTROL"
    assert restored.metadata["adjustment"] == "qfq"
    assert restored.metadata["segment"] == "test"
    assert restored.metadata["transaction_cost_bps"] == 5.0


def test_export_reads_csv_and_adjustment_from_control(tmp_path, market_frame):
    csv_path = tmp_path / "market.csv"
    market_frame.to_csv(csv_path, index=False)
    control = _control(tmp_path, csv_path=str(csv_path), output_root=str(tmp_path / "controlled-provider"))

    export = QlibExport().run("unused.csv", "none", "unused-output", control=control)[0]

    manifest = json.loads((tmp_path / "controlled-provider" / "manifest.json").read_text(encoding="utf-8"))
    assert export["kind"] == "QLIB_EXPORT"
    assert manifest["adjustment"] == "qfq"


def test_model_reads_model_settings_from_control(tmp_path):
    control = _control(tmp_path, model_type="lightgbm", params_json='{"num_leaves": 7}')

    model = QlibModel().run("linear", "{}", control=control)[0]

    assert model["metadata"]["model_type"] == "lightgbm"
    assert model["metadata"]["params"] == {"num_leaves": 7}


def test_control_carries_tushare_pit_and_factor_settings(tmp_path):
    control = _control(
        tmp_path,
        ts_codes="000001.SZ,600000.SH",
        start_date="20240101",
        end_date="20241231",
        snapshot_dir=str(tmp_path / "snapshots"),
        include_events=False,
        adjustment_policy="pit",
        incremental=False,
        factor_set="selected",
        selected_json='["TY_MOM_5"]',
        custom_json="[]",
        factor_output_dir=str(tmp_path / "factors"),
    )

    metadata = control["metadata"]
    assert metadata["ts_codes"] == "000001.SZ,600000.SH"
    assert metadata["start_date"] == "20240101"
    assert metadata["end_date"] == "20241231"
    assert metadata["snapshot_dir"] == str(tmp_path / "snapshots")
    assert metadata["include_events"] is False
    assert metadata["adjustment_policy"] == "pit"
    assert metadata["incremental"] is False
    assert metadata["factor_set"] == "selected"
    assert metadata["selected_json"] == '["TY_MOM_5"]'
    assert metadata["factor_output_dir"] == str(tmp_path / "factors")


def test_control_rejects_invalid_strategy_parameters(tmp_path):
    with pytest.raises(ValueError, match="n_drop"):
        _control(tmp_path, topk=1, n_drop=2)
    with pytest.raises(ValueError, match="交易成本"):
        _control(tmp_path, transaction_cost_bps=float("nan"))


def test_control_rejects_invalid_tushare_window(tmp_path):
    with pytest.raises(ValueError, match="start_date"):
        _control(
            tmp_path,
            csv_path="",
            ts_codes="000001.SZ",
            start_date="20240102",
            end_date="20240101",
        )
