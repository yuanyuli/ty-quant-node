import json

from ty_quant_node.nodes import QlibExport, QlibDataset, QlibModel, QlibTrain, QlibPredict, QlibBacktest, QlibReport


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
