"""线性和 LightGBM 模型后端。"""

from dataclasses import dataclass
import json
from pathlib import Path
import numpy as np
import pandas as pd

from ..core.artifacts import artifact_transaction


@dataclass(frozen=True)
class ModelSpec:
    model_type: str = "linear"
    params: dict | None = None

    def __post_init__(self):
        if self.model_type not in {"linear", "lightgbm"}:
            raise ValueError("model_type 必须是 linear 或 lightgbm")


@dataclass
class TrainedModel:
    spec: ModelSpec
    model: object
    feature_names: list[str]
    artifact_path: Path

    def handle(self, dataset_handle) -> "Handle":
        from ..core.handles import Handle

        return Handle(
            "QLIB_TRAINED_MODEL",
            str(self.artifact_path),
            metadata={
                "dataset_path": dataset_handle.path if hasattr(dataset_handle, "path") else str(dataset_handle),
                "model_type": self.spec.model_type,
                "params": self.spec.params or {},
                "feature_names": self.feature_names,
            },
        )


def train_model(bundle, spec: ModelSpec, artifact_dir: str | Path, *, run_key: str = "") -> TrainedModel:
    train = bundle.dataset.prepare("train")
    train = train.dropna(subset=bundle.feature_names + ["label"])
    if train.empty:
        raise ValueError("训练区间没有可用样本")
    x = train[bundle.feature_names].to_numpy(dtype=float)
    y = train["label"].to_numpy(dtype=float)
    artifact = Path(artifact_dir).resolve()
    if spec.model_type == "linear":
        design = np.c_[np.ones(len(x)), x]
        coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
        model = coefficients
    else:
        from lightgbm import LGBMRegressor

        params = {"n_estimators": 30, "learning_rate": 0.05, "num_leaves": 7, "verbosity": -1}
        params.update(spec.params or {})
        model = LGBMRegressor(random_state=42, **params)
        model.fit(x, y)
    manifest = {
        "schema_version": "1",
        "run_key": str(run_key or ""),
        "model_type": spec.model_type,
        "params": spec.params or {},
        "feature_names": list(bundle.feature_names),
        "rows": int(len(train)),
        "dataset_manifest": bundle.manifest,
    }
    with artifact_transaction(artifact) as staging:
        if spec.model_type == "linear":
            (staging / "model.json").write_text(
                json.dumps({"type": "linear", "feature_names": bundle.feature_names, "coefficients": coefficients.tolist()}),
                encoding="utf-8",
            )
        else:
            model.booster_.save_model(str(staging / "model.txt"))
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return TrainedModel(spec, model, bundle.feature_names, artifact)


def predict_model(trained: TrainedModel, bundle, segment: str = "test") -> pd.DataFrame:
    if segment not in bundle.segments:
        raise ValueError(f"未知数据区间: {segment}")
    start, end = map(pd.Timestamp, bundle.segments[segment])
    frame = bundle.frame[(bundle.frame["datetime"] >= start) & (bundle.frame["datetime"] <= end)].copy()
    frame = frame.dropna(subset=trained.feature_names)
    if frame.empty:
        return pd.DataFrame(columns=["instrument", "datetime", "score", "label"])
    x = frame[trained.feature_names].to_numpy(dtype=float)
    if trained.spec.model_type == "linear":
        scores = np.c_[np.ones(len(x)), x] @ np.asarray(trained.model)
    else:
        scores = trained.model.predict(x)
    return pd.DataFrame({"instrument": frame["instrument"].values, "datetime": frame["datetime"].values, "score": scores, "label": frame["label"].values})


def load_model(handle, dataset_bundle=None) -> TrainedModel:
    """从受控文本 artifact 恢复模型，不加载未知 pickle。"""
    path = Path(handle.path).resolve()
    model_type = str(handle.metadata.get("model_type", "linear"))
    feature_names = list(handle.metadata.get("feature_names") or ["feature_return"])
    spec = ModelSpec(model_type, dict(handle.metadata.get("params") or {}))
    if model_type == "linear":
        payload = json.loads((path / "model.json").read_text(encoding="utf-8"))
        model = np.asarray(payload["coefficients"], dtype=float)
    elif model_type == "lightgbm":
        from lightgbm import Booster

        model = Booster(model_file=str(path / "model.txt"))
    else:
        raise ValueError("不支持的模型类型")
    return TrainedModel(spec, model, feature_names, path)
