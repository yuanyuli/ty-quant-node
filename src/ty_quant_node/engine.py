"""兼容旧 MVP 调用方式的门面；新节点使用 backend 模块。"""

import json
from pathlib import Path
import pandas as pd

from .backend.qlib_backend import build_dataset_from_frame
from .backend.model_backend import ModelSpec, train_model, predict_model
from .backend.backtest_backend import backtest as run_backtest


def build_dataset(raw: pd.DataFrame, adjustment="qfq"):
    bundle = build_dataset_from_frame(raw, adjustment=adjustment)
    return bundle.dataset, bundle.frame


def train_predict(raw: pd.DataFrame, adjustment="qfq"):
    bundle = build_dataset_from_frame(raw, adjustment=adjustment)
    trained = train_model(bundle, ModelSpec("linear", {}), Path(".cache") / "compat-model")
    signal = predict_model(trained, bundle, "test")
    data = bundle.frame.merge(signal[["instrument", "datetime", "score"]], on=["instrument", "datetime"], how="left")
    data["prediction"] = data["score"]
    return {"dataset": bundle.dataset, "data": data, "bundle": bundle, "model": trained, "coef": trained.model.tolist(), "adjustment": adjustment}


def backtest(result, topk=1, initial_cash=1_000_000.0):
    signal = result["data"][["instrument", "datetime", "prediction", "label"]].rename(columns={"prediction": "score"})
    tested = run_backtest(signal, topk=topk, initial_equity=initial_cash)
    return tested.metrics, tested.equity


def save_report(metrics, curve, output_dir):
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    curve.to_csv(out / "equity.csv", index=False)
    return str(out)
