"""Qlib DatasetH 构造；句柄只保存 provider 路径和 schema。"""

from dataclasses import dataclass
import json
from pathlib import Path
import pandas as pd

from ..core.handles import Handle
from ..data import apply_adjustment
from .market import check_provider_consistency, normalize_market_frame


@dataclass
class DatasetBundle:
    dataset: object
    frame: pd.DataFrame
    segments: dict
    feature_names: list[str]
    manifest: dict
    export_path: Path | None = None

    def handle(self) -> Handle:
        backend_name = "qlib" if self.dataset.__class__.__name__ == "DatasetH" else "compat"
        return Handle(
            "QLIB_DATASET",
            str(self.export_path or ""),
            metadata={
                "segments": self.segments,
                "features": self.feature_names,
                "manifest": self.manifest,
                "dataset_backend": backend_name,
                "feature_set_path": str(Path(self.manifest["feature_manifest"]).parent) if self.manifest.get("feature_manifest") else "",
                "label_horizon": self.manifest.get("label_horizon"),
            },
        )


class DatasetHCompat:
    """ComfyUI Python 与共享 Qlib Python 版本不同时使用的最小 DatasetH 契约。"""

    def __init__(self, frame: pd.DataFrame, segments: dict, feature_names: list[str]):
        self._frame = frame.set_index(["datetime", "instrument"])[feature_names + ["label"]].sort_index()
        self.segments = segments

    def prepare(self, segment: str, **_kwargs):
        if segment not in self.segments:
            raise ValueError(f"未知数据区间: {segment}")
        start, end = map(pd.Timestamp, self.segments[segment])
        return self._frame.loc[start:end]


def _default_segments(dates: list[pd.Timestamp]) -> dict:
    n = len(dates)
    train_end = dates[max(0, int(n * 0.6) - 1)]
    valid_end = dates[max(0, int(n * 0.8) - 1)]
    return {"train": (str(dates[0].date()), str(train_end.date())), "valid": (str(train_end.date()), str(valid_end.date())), "test": (str(valid_end.date()), str(dates[-1].date()))}


def _make_dataset(frame: pd.DataFrame, segments: dict, feature_names: list[str]):
    try:
        from qlib.data.dataset import DatasetH
    except ModuleNotFoundError as exc:
        if exc.name != "qlib":
            raise
        return DatasetHCompat(frame, segments, feature_names)

    qframe = frame.set_index(["datetime", "instrument"])[feature_names + ["label"]].sort_index()
    handler_config = {
        "class": "DataHandlerLP",
        "module_path": "qlib.data.dataset.handler",
        "kwargs": {
            "data_loader": {
                "class": "StaticDataLoader",
                "module_path": "qlib.data.dataset.loader",
                "kwargs": {"config": qframe},
            }
        },
    }
    return DatasetH(handler=handler_config, segments=segments)


def build_dataset_from_frame(frame: pd.DataFrame, *, adjustment="qfq", segments=None, allow_unadjusted=False) -> DatasetBundle:
    raw = normalize_market_frame(frame)
    adjusted = apply_adjustment(raw, adjustment, allow_unadjusted=allow_unadjusted)
    adjusted["feature_return"] = adjusted.groupby("instrument")["close"].pct_change().replace([float("inf"), -float("inf")], pd.NA).fillna(0.0)
    adjusted["label"] = adjusted.groupby("instrument")["close"].shift(-1) / adjusted["close"] - 1.0
    dates = sorted(pd.Timestamp(value) for value in adjusted["datetime"].dt.normalize().unique())
    segment_config = segments or _default_segments(dates)
    segment_config = {key: (str(pd.Timestamp(start).date()), str(pd.Timestamp(end).date())) for key, (start, end) in segment_config.items()}
    dataset = _make_dataset(adjusted, segment_config, ["feature_return"])
    return DatasetBundle(dataset, adjusted, segment_config, ["feature_return"], {"adjustment": adjustment, "rows": len(adjusted)}, None)


def build_dataset_from_export(export_path: str | Path, *, segments=None) -> DatasetBundle:
    path = Path(export_path).resolve()
    check_provider_consistency(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    frame = pd.read_parquet(path / "dataset.parquet")
    required = {"instrument", "datetime", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Qlib provider 缺少调整后标签字段: {', '.join(sorted(missing))}")
    adjusted = frame.copy()
    adjusted["datetime"] = pd.to_datetime(adjusted["datetime"]).dt.normalize()
    adjusted["instrument"] = adjusted["instrument"].astype(str).str.upper()
    adjusted = adjusted.sort_values(["instrument", "datetime"]).reset_index(drop=True)
    adjusted["close"] = pd.to_numeric(adjusted["close"], errors="coerce")
    adjusted["feature_return"] = adjusted.groupby("instrument")["close"].pct_change().replace([float("inf"), -float("inf")], pd.NA).fillna(0.0)
    adjusted["label"] = adjusted.groupby("instrument")["close"].shift(-1) / adjusted["close"] - 1.0
    dates = sorted(pd.Timestamp(value) for value in adjusted["datetime"].unique())
    segment_config = segments or _default_segments(dates)
    segment_config = {key: (str(pd.Timestamp(start).date()), str(pd.Timestamp(end).date())) for key, (start, end) in segment_config.items()}
    dataset = _make_dataset(adjusted, segment_config, ["feature_return"])
    return DatasetBundle(dataset, adjusted, segment_config, ["feature_return"], manifest, path)


def build_dataset_from_feature_set(
    export_path: str | Path,
    feature_path: str | Path,
    *,
    segments=None,
    label_horizon: int = 0,
) -> DatasetBundle:
    """将 QLIB_FEATURE_SET 与复权 close 合并为可训练 DatasetH。"""
    export = Path(export_path).resolve()
    feature_root = Path(feature_path).resolve()
    check_provider_consistency(export)
    export_manifest = json.loads((export / "manifest.json").read_text(encoding="utf-8"))
    feature_manifest = json.loads((feature_root / "manifest.json").read_text(encoding="utf-8"))
    market = pd.read_parquet(export / "dataset.parquet")
    features = pd.read_parquet(feature_root / "features.parquet")
    feature_names = list(feature_manifest.get("factor_names") or [])
    if not feature_names:
        raise ValueError("QLIB_FEATURE_SET 没有 factor_names")
    required = {"instrument", "datetime", "close"}
    missing = required - set(market.columns)
    if missing:
        raise ValueError(f"Qlib 数据缺少标签字段: {', '.join(sorted(missing))}")
    data = features.merge(market[["instrument", "datetime", "close"]], on=["instrument", "datetime"], how="left", validate="one_to_one")
    data["datetime"] = pd.to_datetime(data["datetime"]).dt.normalize()
    data["instrument"] = data["instrument"].astype(str).str.upper()
    data = data.sort_values(["instrument", "datetime"]).reset_index(drop=True)
    factor_set = str(feature_manifest.get("factor_set", "ty_factors"))
    horizon = int(label_horizon or (2 if factor_set == "alpha158" else 1))
    if horizon < 1:
        raise ValueError("label_horizon 必须大于 0")
    grouped = data.groupby("instrument", sort=False)["close"]
    if factor_set == "alpha158" and horizon == 2:
        data["label"] = grouped.shift(-2) / grouped.shift(-1) - 1.0
    else:
        data["label"] = grouped.shift(-horizon) / data["close"] - 1.0
    data = data.drop(columns=["close"])
    dates = sorted(pd.Timestamp(value) for value in data["datetime"].unique())
    segment_config = segments or _default_segments(dates)
    segment_config = {key: (str(pd.Timestamp(start).date()), str(pd.Timestamp(end).date())) for key, (start, end) in segment_config.items()}
    dataset = _make_dataset(data, segment_config, feature_names)
    manifest = dict(export_manifest)
    manifest.update({"factor_set": factor_set, "feature_manifest": str(feature_root / "manifest.json"), "label_horizon": horizon})
    bundle = DatasetBundle(dataset, data, segment_config, feature_names, manifest, export)
    return bundle
