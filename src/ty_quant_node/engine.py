"""兼容旧 MVP 调用方式的门面；新节点使用 backend 模块。"""

import json
import hashlib
from pathlib import Path
import pandas as pd

from .backend.qlib_backend import build_dataset_from_frame
from .backend.model_backend import ModelSpec, train_model, predict_model, load_model
from .backend.backtest_backend import backtest as run_backtest
from .core.handles import Handle
from .core.artifacts import artifact_transaction


def build_dataset(raw: pd.DataFrame, adjustment="qfq"):
    bundle = build_dataset_from_frame(raw, adjustment=adjustment)
    return bundle.dataset, bundle.frame


def train_predict(raw: pd.DataFrame, adjustment="qfq"):
    bundle = build_dataset_from_frame(raw, adjustment=adjustment)
    stable = raw.drop(columns=["asof"], errors="ignore").sort_index(axis=1)
    payload = stable.to_json(date_format="iso", orient="records")
    run_key = hashlib.sha256(json.dumps({"frame": payload, "adjustment": adjustment}, sort_keys=True).encode("utf-8")).hexdigest()
    artifact_dir = Path(".cache") / "compat-model" / run_key[:24]
    manifest_path = artifact_dir / "manifest.json"
    model_path = artifact_dir / "model.json"
    if manifest_path.exists() and model_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("run_key") == run_key:
            trained = load_model(
                Handle(
                    "QLIB_TRAINED_MODEL",
                    str(artifact_dir),
                    metadata={"model_type": "linear", "params": {}, "feature_names": manifest.get("feature_names") or bundle.feature_names},
                )
            )
        else:
            trained = train_model(bundle, ModelSpec("linear", {}), artifact_dir, run_key=run_key)
    else:
        trained = train_model(bundle, ModelSpec("linear", {}), artifact_dir, run_key=run_key)
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
    with artifact_transaction(out) as staging:
        (staging / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        curve.to_csv(staging / "equity.csv", index=False)
    return str(out)
