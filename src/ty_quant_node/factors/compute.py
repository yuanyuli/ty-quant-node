"""TY-Factors 和 Alpha158 的 provider 计算后端。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..core.handles import Handle
from ..core.artifacts import artifact_transaction
from .registry import FactorSpec, load_alpha158_specs, load_factor_specs


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _custom_specs(custom: str | dict | list | None) -> list[FactorSpec]:
    if not custom:
        return []
    payload = json.loads(custom) if isinstance(custom, str) else custom
    if isinstance(payload, dict):
        if all(isinstance(expression, str) for expression in payload.values()):
            payload = [
                {"name": name, "version": "custom", "expression": expression, "inputs": [], "lookback": 0}
                for name, expression in payload.items()
            ]
        else:
            payload = [dict(value, name=name) for name, value in payload.items() if isinstance(value, dict)]
    if not isinstance(payload, list):
        raise ValueError("custom 因子必须是对象或数组")
    specs: list[FactorSpec] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("custom 因子数组元素必须是对象")
        required = {"name", "expression"}
        if required - set(item):
            raise ValueError("custom 因子缺少 name 或 expression")
        inputs = item.get("inputs") or []
        specs.append(
            FactorSpec(
                name=str(item["name"]),
                version=str(item.get("version", "custom")),
                expression=str(item["expression"]),
                inputs=tuple(str(value).lstrip("$") for value in inputs),
                lookback=int(item.get("lookback", 0)),
                adjustment_policy=str(item.get("adjustment_policy", "point_in_time")),
                null_policy=str(item.get("null_policy", "drop")),
                category=str(item.get("category", "custom")),
            )
        )
    return specs


def select_factor_specs(factor_set: str, selected: str | list[str] | None = None, custom: str | dict | list | None = None) -> list[FactorSpec]:
    if factor_set not in {"ty_factors", "alpha158", "selected", "custom"}:
        raise ValueError("不支持的 factor_set")
    ty_specs = load_factor_specs()
    if factor_set == "ty_factors":
        return ty_specs
    if factor_set == "alpha158":
        return load_alpha158_specs()
    if factor_set == "custom":
        specs = _custom_specs(custom)
    else:
        names = json.loads(selected) if isinstance(selected, str) else (selected or [])
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise ValueError("selected 因子必须是字符串数组")
        all_specs = ty_specs + load_alpha158_specs()
        by_name = {spec.name: spec for spec in all_specs}
        missing = [name for name in names if name not in by_name]
        if missing:
            raise ValueError(f"因子不存在: {', '.join(missing)}")
        specs = [by_name[name] for name in names]
    if not specs:
        raise ValueError("没有可计算的因子")
    names_seen: set[str] = set()
    for spec in specs:
        if spec.name in names_seen:
            raise ValueError(f"因子名称重复: {spec.name}")
        names_seen.add(spec.name)
    return specs


def _direct_ty_factor(frame: pd.DataFrame, spec: FactorSpec) -> pd.Series:
    ordered = frame.sort_values(["instrument", "datetime"])
    groups = ordered.groupby("instrument", sort=False)
    if spec.name.startswith("TY_MOM_"):
        window = int(spec.name.rsplit("_", 1)[1])
        lagged = groups["ty_close"].shift(window)
        values = ordered["ty_close"] / lagged.where(lagged != 0) - 1.0
    elif spec.name == "TY_VOL_20":
        returns = groups["ty_close"].pct_change()
        values = returns.groupby(ordered["instrument"], sort=False).rolling(20, min_periods=20).std().reset_index(level=0, drop=True)
        values.index = ordered.index
    elif spec.name == "TY_VOLUME_RATIO_20":
        mean = groups["ty_volume"].rolling(20, min_periods=20).mean().reset_index(level=0, drop=True)
        mean.index = ordered.index
        values = ordered["ty_volume"] / mean
    else:
        raise ValueError(f"兼容模式不支持因子表达式: {spec.name}")
    result = pd.Series(values.to_numpy(), index=ordered.index)
    return result.reindex(frame.index)


def _provider_instruments(provider: Path) -> list[str]:
    path = provider / "instruments" / "all.txt"
    if not path.exists():
        raise ValueError(f"Qlib instruments 不存在: {path}")
    return [line.split("\t", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _qlib_features(provider: Path, specs: list[FactorSpec], frame: pd.DataFrame) -> pd.DataFrame:
    try:
        import qlib
        from qlib.data.dataset.loader import QlibDataLoader
    except ModuleNotFoundError as exc:
        raise RuntimeError("当前 Python 环境没有 Qlib，无法计算 Alpha158/custom 因子") from exc
    try:
        qlib.init(provider_uri=str(provider), region="cn", dataset_cache=None, expression_cache=None, clear_mem_cache=True)
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Qlib 初始化失败: {type(exc).__name__}: {exc}") from exc
    dates = pd.to_datetime(frame["datetime"])
    loader = QlibDataLoader(config={"feature": ([spec.expression for spec in specs], [spec.name for spec in specs])})
    loaded = loader.load(
        instruments=_provider_instruments(provider),
        start_time=str(dates.min().date()),
        end_time=str(dates.max().date()),
    )
    if isinstance(loaded.columns, pd.MultiIndex):
        loaded.columns = [column[-1] for column in loaded.columns]
    loaded = loaded.reset_index()
    loaded["datetime"] = pd.to_datetime(loaded["datetime"]).dt.normalize()
    loaded["instrument"] = loaded["instrument"].astype(str).str.upper()
    return frame[["instrument", "datetime"]].merge(loaded, on=["instrument", "datetime"], how="left", validate="one_to_one")


def compute_ty_factors(
    provider_path: str | Path,
    *,
    factor_set: str = "ty_factors",
    selected: str | list[str] | None = None,
    custom: str | dict | list | None = None,
    output_dir: str | Path,
) -> Handle:
    provider = Path(provider_path).resolve()
    manifest_path = provider / "manifest.json"
    data_path = provider / "dataset.parquet"
    if not manifest_path.exists() or not data_path.exists():
        raise ValueError("QLIB_EXPORT 缺少 manifest.json 或 dataset.parquet")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("adjustment") == "none":
        raise ValueError("因子计算拒绝未复权 provider，请先使用 PIT 或 vendor 复权")
    if factor_set == "ty_factors" and not bool(manifest.get("point_in_time", False)):
        raise ValueError("TY-Factors 默认要求 point-in-time provider；如需供应商 qfq 请显式选择 alpha158/custom")
    specs = select_factor_specs(factor_set, selected, custom)
    frame = pd.read_parquet(data_path)
    frame["datetime"] = pd.to_datetime(frame["datetime"]).dt.normalize()
    frame["instrument"] = frame["instrument"].astype(str).str.upper()
    key = _hash_payload({"provider": manifest.get("files", manifest.get("raw_hash")), "factor_set": factor_set, "specs": [spec.__dict__ for spec in specs]})
    base_output = Path(output_dir).resolve()
    output = base_output
    result_path = output / "features.parquet"
    result_manifest_path = output / "manifest.json"
    if result_manifest_path.exists() and result_path.exists():
        cached = json.loads(result_manifest_path.read_text(encoding="utf-8"))
        if cached.get("cache_key") == key:
            return Handle("QLIB_FEATURE_SET", str(output), metadata=cached)
        output = base_output / key[:24]
    elif base_output.exists() and any(base_output.iterdir()):
        output = base_output / key[:24]

    result = frame[["instrument", "datetime"]].copy()
    if factor_set == "ty_factors":
        required = {"ty_close", "ty_volume"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"PIT provider 缺少字段: {', '.join(sorted(missing))}")
        for spec in specs:
            result[spec.name] = _direct_ty_factor(frame, spec)
    elif factor_set == "selected" and all(spec.name.startswith("TY_") for spec in specs) and {"ty_close", "ty_volume"}.issubset(frame.columns):
        for spec in specs:
            result[spec.name] = _direct_ty_factor(frame, spec)
    else:
        result = _qlib_features(provider, specs, frame)

    quality = {spec.name: int(result[spec.name].isna().sum()) for spec in specs}
    output_manifest = {
        "schema_version": "1",
        "cache_key": key,
        "provider_path": str(provider),
        "provider_snapshot_id": manifest.get("snapshot_id"),
        "factor_set": factor_set,
        "factor_count": len(specs),
        "factor_names": [spec.name for spec in specs],
        "factors": [spec.__dict__ for spec in specs],
        "quality_nan_counts": quality,
        "rows": len(result),
    }
    with artifact_transaction(output) as staging:
        result.to_parquet(staging / "features.parquet", index=False)
        (staging / "manifest.json").write_text(
            json.dumps(output_manifest, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    return Handle("QLIB_FEATURE_SET", str(output), metadata=output_manifest)
