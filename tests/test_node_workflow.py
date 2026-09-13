import json
from pathlib import Path
import pytest
import pandas as pd

from ty_quant_node.nodes import QlibExport, QlibDataset, QlibModel, QlibTrain, QlibPredict, QlibBacktest, QlibReport
from ty_quant_node.core.report import create_report
from ty_quant_node.backend.backtest_backend import BacktestResult


def test_nodes_execute_complete_fixture_workflow(tmp_path, market_frame):
    csv_path = tmp_path / "market.csv"
    market_frame.to_csv(csv_path, index=False)
    export = QlibExport().run(str(csv_path), "qfq", str(tmp_path / "provider"))[0]
    dataset = QlibDataset().run(export, "2024-01-01", "2024-01-03", "2024-01-04", "2024-01-06")[0]
    model = QlibModel().run("linear", "{}")[0]
    trained, summary = QlibTrain().run(dataset, model, str(tmp_path / "model"))
    signal = QlibPredict().run(trained, dataset, "test")[0]
    result, metrics_json = QlibBacktest().run(signal, 1, 0, 5.0)
    summary_json, image, text = QlibReport().run(result, str(tmp_path / "report"))
    assert json.loads(summary)["model_type"] == "linear"
    assert json.loads(metrics_json)["days"] >= 1
    assert json.loads(summary_json)["days"] >= 1
    assert image.shape[-1] == 3
    assert text
    assert (tmp_path / "model" / "manifest.json").exists()
    assert (Path(signal["path"]).parent / "backtest" / "manifest.json").exists()
    assert (tmp_path / "report" / "manifest.json").exists()
    assert json.loads((tmp_path / "model" / "manifest.json").read_text(encoding="utf-8"))["files"]["model"]
    backtest_manifest = Path(result["path"]) / "manifest.json"
    assert json.loads(backtest_manifest.read_text(encoding="utf-8"))["files"]["metrics"]
    assert json.loads((tmp_path / "report" / "manifest.json").read_text(encoding="utf-8"))["files"]["equity"]


def test_dataset_rejects_partial_date_configuration(tmp_path, market_frame):
    csv_path = tmp_path / "market.csv"
    market_frame.to_csv(csv_path, index=False)
    export = QlibExport().run(str(csv_path), "qfq", str(tmp_path / "provider"))[0]
    with pytest.raises(ValueError, match="训练和测试区间必须同时填写"):
        QlibDataset().run(export, "2024-01-01", "", "", "")


def test_pipeline_reuses_same_model_version_and_versions_changed_parameters(tmp_path, market_frame):
    csv_path = tmp_path / "market.csv"
    market_frame.to_csv(csv_path, index=False)
    export = QlibExport().run(str(csv_path), "qfq", str(tmp_path / "provider"))[0]
    dataset = QlibDataset().run(export, "2024-01-01", "2024-01-03", "2024-01-04", "2024-01-06")[0]

    first_model = QlibModel().run("linear", "{}")[0]
    first = QlibTrain().run(dataset, first_model, str(tmp_path / "model"))[0]
    repeated = QlibTrain().run(dataset, first_model, str(tmp_path / "model"))[0]
    changed_model = QlibModel().run("linear", '{"regularization": 1}')[0]
    changed = QlibTrain().run(dataset, changed_model, str(tmp_path / "model"))[0]

    assert repeated["path"] == first["path"]
    assert changed["path"] != first["path"]
    assert (tmp_path / "model" / "manifest.json").exists()


def test_prediction_artifact_is_versioned_and_reused(tmp_path, market_frame):
    csv_path = tmp_path / "market.csv"
    market_frame.to_csv(csv_path, index=False)
    export = QlibExport().run(str(csv_path), "qfq", str(tmp_path / "provider"))[0]
    dataset = QlibDataset().run(export, "2024-01-01", "2024-01-03", "2024-01-04", "2024-01-06")[0]
    model = QlibModel().run("linear", "{}")[0]
    trained = QlibTrain().run(dataset, model, str(tmp_path / "model"))[0]

    first = QlibPredict().run(trained, dataset, "test")[0]
    second = QlibPredict().run(trained, dataset, "test")[0]

    assert first["path"] == second["path"]
    signal_path = Path(first["path"])
    assert signal_path.name == "signal.parquet"
    assert signal_path.parent.parent.name == "signals"
    manifest = json.loads((signal_path.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_key"] == first["metadata"]["run_key"]
    assert manifest["files"]["signal"] == first["metadata"]["files"]["signal"]


def test_backtest_and_report_reuse_matching_run_versions(tmp_path, market_frame):
    csv_path = tmp_path / "market.csv"
    market_frame.to_csv(csv_path, index=False)
    export = QlibExport().run(str(csv_path), "qfq", str(tmp_path / "provider"))[0]
    dataset = QlibDataset().run(export, "2024-01-01", "2024-01-03", "2024-01-04", "2024-01-06")[0]
    model = QlibModel().run("linear", "{}")[0]
    trained = QlibTrain().run(dataset, model, str(tmp_path / "model"))[0]
    signal = QlibPredict().run(trained, dataset, "test")[0]

    first = QlibBacktest().run(signal, 1, 0, 5.0)[0]
    repeated = QlibBacktest().run(signal, 1, 0, 5.0)[0]
    changed = QlibBacktest().run(signal, 2, 0, 5.0)[0]
    QlibReport().run(first, str(tmp_path / "report"))
    QlibReport().run(first, str(tmp_path / "report"))

    assert repeated["path"] == first["path"]
    assert changed["path"] != first["path"]
    assert (tmp_path / "report" / "manifest.json").exists()


def test_report_coerces_string_dates_to_datetime_before_plotting(tmp_path, monkeypatch):
    import matplotlib.axes

    plotted = []
    original_plot = matplotlib.axes.Axes.plot

    def spy_plot(self, *args, **kwargs):
        plotted.append(args[0])
        return original_plot(self, *args, **kwargs)

    monkeypatch.setattr(matplotlib.axes.Axes, "plot", spy_plot)
    result = BacktestResult(
        {"total_return": 0.0},
        pd.DataFrame({"datetime": ["2024-01-01", "2024-01-02"], "equity": [1.0, 1.01]}),
        pd.DataFrame(),
    )
    create_report(result, tmp_path / "report")
    assert plotted
    assert pd.api.types.is_datetime64_any_dtype(pd.Series(plotted[0]))
