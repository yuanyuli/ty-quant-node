import json
import pandas as pd
import pytest

from ty_quant_node.backend.qlib_backend import build_dataset_from_frame
from ty_quant_node.backend.qlib_backend import build_dataset_from_export
from ty_quant_node.nodes import QlibExport
from ty_quant_node.backend.model_backend import ModelSpec, train_model, predict_model
from ty_quant_node.backend.backtest_backend import backtest
from ty_quant_node.core.report import create_report, image_to_tensor


def test_dataset_model_prediction_backtest_report(tmp_path, market_frame):
    bundle = build_dataset_from_frame(
        market_frame,
        adjustment="qfq",
        segments={"train": ("2024-01-01", "2024-01-03"), "test": ("2024-01-04", "2024-01-06")},
    )
    prepared = bundle.dataset.prepare("train")
    assert isinstance(prepared, pd.DataFrame)
    assert "label" in prepared.columns
    assert bundle.dataset.__class__.__name__ in {"DatasetH", "DatasetHCompat"}
    trained = train_model(bundle, ModelSpec("linear", {}), tmp_path / "model")
    signal = predict_model(trained, bundle, "test")
    assert {"instrument", "datetime", "score"}.issubset(signal.columns)
    result = backtest(signal, bundle.frame, topk=1, transaction_cost_bps=5)
    assert "total_return" in result.metrics
    report = create_report(result, tmp_path / "report")
    assert json.loads((tmp_path / "report" / "summary.json").read_text(encoding="utf-8"))["days"] >= 1
    tensor = image_to_tensor(report.image_path)
    assert tensor.ndim == 4 and tensor.shape[-1] == 3


def test_export_dataset_labels_use_adjusted_provider_close_across_factor_change(tmp_path, market_frame):
    csv_path = tmp_path / "market.csv"
    market_frame.to_csv(csv_path, index=False)
    export = QlibExport().run(str(csv_path), "qfq", str(tmp_path / "provider"))[0]

    bundle = build_dataset_from_export(
        export["path"],
        segments={"train": ("2024-01-01", "2024-01-02"), "test": ("2024-01-03", "2024-01-04")},
    )
    test_rows = bundle.dataset.prepare("test").reset_index()
    aaa = test_rows[(test_rows["instrument"] == "AAA") & (test_rows["datetime"] == pd.Timestamp("2024-01-03"))].iloc[0]

    # QFQ anchor=2: 2024-01-03 adjusted close=12*0.5=6, next=13*1=13.
    assert aaa["label"] == pytest.approx(13.0 / 6.0 - 1.0)


def test_lightgbm_model_predicts(market_frame, tmp_path):
    pytest.importorskip("lightgbm")
    bundle = build_dataset_from_frame(market_frame, adjustment="qfq", segments={"train": ("2024-01-01", "2024-01-04"), "test": ("2024-01-05", "2024-01-06")})
    trained = train_model(bundle, ModelSpec("lightgbm", {"n_estimators": 5}), tmp_path / "lgb")
    signal = predict_model(trained, bundle, "test")
    assert len(signal) == 4
    assert (tmp_path / "lgb" / "model.txt").exists()
