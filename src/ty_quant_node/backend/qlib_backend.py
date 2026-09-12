"""Qlib DatasetH 构造；句柄只保存 provider 路径和 schema。"""

from dataclasses import dataclass
import json
from pathlib import Path
import pandas as pd

from ..core.handles import Handle
from ..data import apply_adjustment
from .market import normalize_market_frame


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
            metadata={"segments": self.segments, "features": self.feature_names, "manifest": self.manifest, "dataset_backend": backend_name},
        )


class DatasetHCompat:
    """ComfyUI Python 与共享 Qlib Python 版本不同时使用的最小 DatasetH 契约。"""

    def __init__(self, frame: pd.DataFrame, segments: dict):
        self._frame = frame.set_index(["datetime", "instrument"])[["feature_return", "label"]].sort_index()
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


def _make_dataset(frame: pd.DataFrame, segments: dict):
    try:
        from qlib.data.dataset import DatasetH
    except ModuleNotFoundError as exc:
        if exc.name != "qlib":
            raise
        return DatasetHCompat(frame, segments)

    qframe = frame.set_index(["datetime", "instrument"])[["feature_return", "label"]].sort_index()
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
    dataset = _make_dataset(adjusted, segment_config)
    return DatasetBundle(dataset, adjusted, segment_config, ["feature_return"], {"adjustment": adjustment, "rows": len(adjusted)}, None)


def build_dataset_from_export(export_path: str | Path, *, segments=None) -> DatasetBundle:
    path = Path(export_path).resolve()
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    frame = pd.read_parquet(path / "dataset.parquet")
    adjustment = str(manifest.get("adjustment", "qfq"))
    bundle = build_dataset_from_frame(frame, adjustment="none", segments=segments, allow_unadjusted=True)
    bundle.export_path = path
    bundle.manifest = manifest
    return bundle
