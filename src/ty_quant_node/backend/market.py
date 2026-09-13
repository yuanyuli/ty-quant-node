"""市场数据校验和 Qlib 本地 provider 导出。"""

import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

from ..core.handles import Handle
from ..core.artifacts import artifact_transaction, sha256_file
from ..data import apply_adjustment


ALIASES = {
    "ts_code": "instrument",
    "trade_date": "datetime",
    "open": "open_raw",
    "high": "high_raw",
    "low": "low_raw",
    "close": "close_raw",
    "vol": "volume_raw",
    "volume": "volume_raw",
    "amount": "amount_raw",
}
RAW_FIELDS = ["open_raw", "high_raw", "low_raw", "close_raw", "volume_raw"]


def normalize_market_frame(frame: pd.DataFrame) -> pd.DataFrame:
    rename = {key: value for key, value in ALIASES.items() if key in frame.columns and value not in frame.columns}
    out = frame.rename(columns=rename).copy()
    required = {"instrument", "datetime", *RAW_FIELDS}
    missing = required - set(out.columns)
    if missing:
        raise ValueError(f"行情数据缺少字段: {', '.join(sorted(missing))}")
    out["datetime"] = pd.to_datetime(out["datetime"].astype(str))
    out["instrument"] = out["instrument"].astype(str).str.strip().str.upper()
    for field in RAW_FIELDS + ["amount_raw", "adj_factor"]:
        if field in out:
            out[field] = pd.to_numeric(out[field], errors="coerce")
    if "amount_raw" not in out:
        out["amount_raw"] = np.nan
    return out.sort_values(["datetime", "instrument"]).reset_index(drop=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frame_hash(frame: pd.DataFrame) -> str:
    values = pd.util.hash_pandas_object(frame.sort_index(axis=1), index=True).values.tobytes()
    return hashlib.sha256(values).hexdigest()


def _write_bin(path: Path, values: np.ndarray, start_index: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.hstack(([float(start_index)], np.asarray(values, dtype=np.float32))).astype("<f4").tofile(path)


def _write_qlib_artifact(
    adjusted: pd.DataFrame,
    raw: pd.DataFrame,
    output: Path,
    adjustment: str,
    run_key: str = "",
) -> dict:
    """把已校验的 provider 写入 staging 目录并返回 manifest。"""

    adjusted["datetime"] = adjusted["datetime"].dt.normalize()
    calendar = sorted(pd.to_datetime(adjusted["datetime"]).dt.normalize().unique())
    if not calendar:
        raise ValueError("行情数据为空")
    calendar_strings = [pd.Timestamp(value).strftime("%Y-%m-%d") for value in calendar]
    (output / "calendars").mkdir(exist_ok=True)
    (output / "calendars" / "day.txt").write_text("\n".join(calendar_strings) + "\n", encoding="utf-8")
    (output / "instruments").mkdir(exist_ok=True)
    instruments = []
    for instrument, group in adjusted.groupby("instrument", sort=True):
        first = pd.Timestamp(group["datetime"].min()).strftime("%Y-%m-%d")
        last = pd.Timestamp(group["datetime"].max()).strftime("%Y-%m-%d")
        instruments.append(f"{instrument}\t{first}\t{last}")
    (output / "instruments" / "all.txt").write_text("\n".join(instruments) + "\n", encoding="utf-8")
    field_map = {"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume", "factor": "factor", "vwap": "vwap"}
    extra_fields = {column: column for column in adjusted.columns if column.startswith("ty_")}
    field_map.update(extra_fields)
    for instrument, group in adjusted.groupby("instrument", sort=True):
        group = group.set_index("datetime").sort_index()
        instrument_dir = output / "features" / instrument.lower()
        for qlib_field, column in field_map.items():
            if column not in group:
                continue
            values = group[column].reindex(calendar).to_numpy(dtype=np.float32)
            _write_bin(instrument_dir / f"{qlib_field}.day.bin", values)
    dataset_frame = adjusted.copy()
    dataset_frame.to_parquet(output / "dataset.parquet", index=False)
    manifest = {
        "schema_version": "1",
        "source": str(adjusted["source"].dropna().iloc[0]) if "source" in adjusted and not adjusted["source"].dropna().empty else "local",
        "pulled_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "calendar_count": len(calendar),
        "instrument_count": int(adjusted["instrument"].nunique()),
        "row_count": len(adjusted),
        "date_range": [calendar_strings[0], calendar_strings[-1]],
        "adjustment": adjustment,
        "point_in_time": bool(adjusted.attrs.get("point_in_time", False)),
        "adjustment_source": adjusted.attrs.get("adjustment_source"),
        "event_count": int(adjusted.attrs.get("event_count", 0)),
        "factor_definition": adjusted.attrs.get("factor_definition", "adjusted/original"),
        "snapshot_id": adjusted.attrs.get("snapshot_id"),
        "anchor_factor": adjusted.attrs.get("adjustment_anchor_factor"),
        "anchor_date": adjusted.attrs.get("adjustment_anchor_date"),
        "quality_errors": adjusted.attrs.get("quality_errors", 0),
        "raw_hash": _frame_hash(raw),
        "factor_hash": _frame_hash(raw[["instrument", "datetime", "adj_factor"]]) if "adj_factor" in raw else None,
        "run_key": str(run_key or ""),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["files"] = {
        "calendar": _sha256_file(output / "calendars" / "day.txt"),
        "instruments": _sha256_file(output / "instruments" / "all.txt"),
        "dataset": _sha256_file(output / "dataset.parquet"),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def export_qlib(
    frame: pd.DataFrame,
    output_dir: str | Path,
    *,
    adjustment="qfq",
    allow_unadjusted=False,
    run_key: str = "",
) -> Handle:
    raw = normalize_market_frame(frame)
    if adjustment == "pit":
        required = {"ty_open", "ty_high", "ty_low", "ty_close", "ty_volume", "ty_price_factor"}
        missing = required - set(raw.columns)
        if missing:
            raise ValueError(f"PIT 行情缺少字段: {', '.join(sorted(missing))}")
        adjusted = raw.copy()
        for standard, pit_name in {
            "open": "ty_open",
            "high": "ty_high",
            "low": "ty_low",
            "close": "ty_close",
            "volume": "ty_volume",
        }.items():
            adjusted[standard] = pd.to_numeric(adjusted[pit_name], errors="coerce")
        adjusted["factor"] = pd.to_numeric(adjusted["ty_price_factor"], errors="coerce")
        if "ty_vwap" in adjusted:
            adjusted["vwap"] = pd.to_numeric(adjusted["ty_vwap"], errors="coerce")
        adjusted.attrs.update(raw.attrs)
        adjusted.attrs.update(
            {
                "adjustment": "pit",
                "point_in_time": bool(raw.attrs.get("point_in_time", False)),
                "adjustment_source": raw.attrs.get("adjustment_source"),
                "event_count": int(raw.attrs.get("event_count", 0)),
                "factor_definition": "ty_price_adjusted/original",
            }
        )
    else:
        adjusted = apply_adjustment(raw, adjustment, allow_unadjusted=allow_unadjusted)
    output = Path(output_dir).resolve()
    with artifact_transaction(output) as staging:
        manifest = _write_qlib_artifact(adjusted, raw, staging, adjustment, run_key=run_key)
    return Handle("QLIB_EXPORT", str(output), metadata=manifest)


def check_provider_consistency(provider_dir: str | Path) -> dict:
    provider = Path(provider_dir)
    manifest_path = provider / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Qlib manifest 无法读取: {manifest_path}") from exc
        manifest_files = manifest.get("files") or {}
        file_paths = {
            "calendar": provider / "calendars" / "day.txt",
            "instruments": provider / "instruments" / "all.txt",
            "dataset": provider / "dataset.parquet",
        }
        for name, expected in manifest_files.items():
            path = file_paths.get(name)
            if path is None or not path.exists() or sha256_file(path) != str(expected):
                raise ValueError(f"Qlib provider 文件 hash 不匹配: {name}")
    calendar = [line.strip() for line in (provider / "calendars" / "day.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    if calendar != sorted(calendar) or len(set(calendar)) != len(calendar):
        raise ValueError("Qlib calendar 必须严格升序且无重复")
    instruments = [line.split("\t")[0] for line in (provider / "instruments" / "all.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    feature_dirs = sorted(path.name.upper() for path in (provider / "features").iterdir() if path.is_dir())
    if sorted(instruments) != feature_dirs:
        raise ValueError("instruments 与 features 目录集合不一致")
    expected_length = len(calendar)
    for instrument_dir in (provider / "features").iterdir():
        for feature_path in instrument_dir.glob("*.day.bin"):
            values = np.fromfile(feature_path, dtype="<f4")
            if len(values) < 1:
                raise ValueError(f"Qlib feature 文件为空: {feature_path.name}")
            start_index = int(values[0])
            if start_index < 0 or start_index + len(values) - 1 > expected_length:
                raise ValueError(f"Qlib feature 与 calendar 长度不一致: {feature_path.name}")
    return {"calendar_count": len(calendar), "instrument_count": len(instruments), "consistent": True}
