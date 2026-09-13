import json
import pytest

from ty_quant_node.core.handles import Handle
from ty_quant_node.nodes import QlibControl, QlibExport, QlibModel


def _control(tmp_path, **overrides):
    values = {
        "data_source": "local_csv",
        "csv_path": str(tmp_path / "market.csv"),
        "ts_codes": "000001.SZ",
        "query_start": "2024-01-01",
        "query_end": "2024-12-31",
        "adjustment_mode": "vendor_qfq",
        "include_events": True,
        "incremental": True,
        "train_start": "2024-01-01",
        "train_end": "2024-01-03",
        "test_start": "2024-01-04",
        "test_end": "2024-01-06",
        "factor_set": "ty_factors",
        "selected_json": "[]",
        "custom_json": "[]",
        "model_type": "linear",
        "params_json": "{}",
        "segment": "test",
        "topk": 1,
        "n_drop": 0,
        "transaction_cost_bps": 5.0,
        "artifact_root": str(tmp_path / "artifacts"),
    }
    values.update(overrides)
    return QlibControl().run(**values)[0]


def test_control_node_returns_versioned_handle(tmp_path):
    control = _control(tmp_path)

    restored = Handle.from_dict(json.loads(json.dumps(control)))

    assert restored.kind == "QLIB_CONTROL"
    assert restored.metadata["config_schema_version"] == "2"
    assert restored.metadata["adjustment_mode"] == "vendor_qfq"
    assert restored.metadata["segment"] == "test"
    assert restored.metadata["transaction_cost_bps"] == 5.0
    assert __import__("pathlib").Path(restored.metadata["provider_dir"]).name == "provider"
    assert __import__("pathlib").Path(restored.metadata["snapshot_dir"]).name == "snapshots"
    assert __import__("pathlib").Path(restored.metadata["factor_dir"]).name == "factors"
    assert __import__("pathlib").Path(restored.metadata["model_dir"]).name == "model"
    assert __import__("pathlib").Path(restored.metadata["report_dir"]).name == "report"


def test_export_reads_csv_and_adjustment_from_control(tmp_path, market_frame):
    csv_path = tmp_path / "market.csv"
    market_frame.to_csv(csv_path, index=False)
    control = _control(tmp_path, csv_path=str(csv_path), artifact_root=str(tmp_path / "controlled-artifacts"))

    export = QlibExport().run("unused.csv", "none", "unused-output", control=control)[0]

    manifest = json.loads((tmp_path / "controlled-artifacts" / "provider" / "manifest.json").read_text(encoding="utf-8"))
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
        data_source="tushare", ts_codes="000001.SZ,600000.SH",
        query_start="2024-01-01",
        query_end="2024-12-31",
        artifact_root=str(tmp_path / "artifacts"),
        include_events=False,
        adjustment_mode="pit",
        incremental=False,
        factor_set="selected",
        selected_json='["TY_MOM_5"]',
        custom_json="[]",
    )

    metadata = control["metadata"]
    assert metadata["ts_codes"] == "000001.SZ,600000.SH"
    assert metadata["query_start"] == "2024-01-01"
    assert metadata["query_end"] == "2024-12-31"
    assert __import__("pathlib").Path(metadata["snapshot_dir"]).name == "snapshots"
    assert metadata["include_events"] is False
    assert metadata["adjustment_mode"] == "pit"
    assert metadata["incremental"] is False
    assert metadata["factor_set"] == "selected"
    assert metadata["selected_json"] == '["TY_MOM_5"]'
    assert __import__("pathlib").Path(metadata["factor_dir"]).name == "factors"


def test_control_rejects_invalid_strategy_parameters(tmp_path):
    with pytest.raises(ValueError, match="n_drop"):
        _control(tmp_path, topk=1, n_drop=2)
    with pytest.raises(ValueError, match="交易成本"):
        _control(tmp_path, transaction_cost_bps=float("nan"))


def test_control_rejects_invalid_tushare_window(tmp_path):
    with pytest.raises(ValueError, match="query_start"):
        _control(tmp_path, data_source="tushare", query_start="2024-01-02", query_end="2024-01-01")


def test_control_rejects_missing_source_specific_input(tmp_path):
    with pytest.raises(ValueError, match="csv_path"):
        _control(tmp_path, data_source="local_csv", csv_path="")
    with pytest.raises(ValueError, match="ts_codes"):
        _control(tmp_path, data_source="tushare", ts_codes="")


def test_control_input_contract_has_groupable_tooltips():
    definitions = QlibControl.INPUT_TYPES()
    all_specs = {**definitions["required"], **definitions["optional"]}
    old_names = {"adjustment", "adjustment_policy", "output_root", "snapshot_dir", "factor_output_dir", "artifact_dir", "report_dir", "start_date", "end_date"}
    assert not old_names.intersection(all_specs)
    assert set(all_specs) == {
        "data_source", "csv_path", "ts_codes", "query_start", "query_end",
        "adjustment_mode", "include_events", "incremental", "train_start", "train_end",
        "test_start", "test_end", "factor_set", "selected_json", "custom_json",
        "model_type", "params_json", "segment", "topk", "n_drop",
        "transaction_cost_bps", "artifact_root",
    }
    assert all("tooltip" in (spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}) for spec in all_specs.values())
