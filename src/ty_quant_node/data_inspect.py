"""行情抽样图表和数据质量审计。"""

import json
from pathlib import Path

import pandas as pd

from .backend.market import normalize_market_frame, check_provider_consistency
from .core.artifacts import artifact_transaction, sha256_file


def inspect_frame(frame: pd.DataFrame, *, instrument: str = "", lookback: int = 120) -> tuple[pd.DataFrame, dict]:
    data = normalize_market_frame(frame)
    selected = str(instrument or "").strip().upper()
    if not selected:
        selected = str(data["instrument"].iloc[0])
    sample = data[data["instrument"] == selected].sort_values("datetime").tail(int(lookback)).copy()
    if sample.empty:
        raise ValueError(f"找不到股票: {selected}")
    duplicate_count = int(data.duplicated(["instrument", "datetime"]).sum())
    invalid_ohlc = int(((data["high_raw"] < data[["open_raw", "close_raw"]].max(axis=1)) | (data["low_raw"] > data[["open_raw", "close_raw"]].min(axis=1))).sum())
    audit = {
        "schema_version": "1",
        "instrument": selected,
        "rows": int(len(sample)),
        "total_rows": int(len(data)),
        "instrument_count": int(data["instrument"].nunique()),
        "date_range": [str(data["datetime"].min().date()), str(data["datetime"].max().date())],
        "sample_date_range": [str(sample["datetime"].min().date()), str(sample["datetime"].max().date())],
        "duplicate_count": duplicate_count,
        "missing_adj_factor_count": int(data.get("adj_factor", pd.Series(index=data.index, dtype=float)).isna().sum()),
        "zero_adj_factor_count": int((data.get("adj_factor", pd.Series(index=data.index, dtype=float)) == 0).sum()),
        "invalid_ohlc_count": invalid_ohlc,
        "status": "ok" if duplicate_count == 0 and invalid_ohlc == 0 else "warning",
    }
    return sample, audit


def create_inspection(frame: pd.DataFrame, output_dir: str | Path, *, instrument: str = "", lookback: int = 120, source_kind: str = ""):
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    sample, audit = inspect_frame(frame, instrument=instrument, lookback=lookback)
    audit["source_kind"] = source_kind
    output = Path(output_dir).resolve()
    with artifact_transaction(output) as staging:
        fig, (ax, volume_ax) = plt.subplots(2, 1, figsize=(10, 6), dpi=120, sharex=True, gridspec_kw={"height_ratios": [3, 1]})
        x = range(len(sample))
        for i, (_, row) in enumerate(sample.reset_index(drop=True).iterrows()):
            color = "#d94841" if row["close_raw"] >= row["open_raw"] else "#2f9e44"
            ax.vlines(i, row["low_raw"], row["high_raw"], color=color, linewidth=1)
            bottom = min(row["open_raw"], row["close_raw"])
            height = max(abs(row["close_raw"] - row["open_raw"]), 1e-8)
            ax.add_patch(Rectangle((i - 0.3, bottom), 0.6, height, facecolor=color, edgecolor=color, alpha=0.85))
        ax.set_title(f"{audit['instrument']} K-line sample ({audit['sample_date_range'][0]} to {audit['sample_date_range'][1]})")
        ax.set_ylabel("Price")
        ax.grid(alpha=0.2)
        volume_ax.bar(list(x), sample["volume_raw"].fillna(0), color="#64748b", alpha=0.7)
        volume_ax.set_ylabel("Volume")
        volume_ax.set_xticks(list(x)[:: max(1, len(sample) // 8)])
        volume_ax.set_xticklabels([str(value.date()) for value in sample["datetime"].iloc[:: max(1, len(sample) // 8)]], rotation=30, ha="right")
        volume_ax.grid(alpha=0.15)
        fig.tight_layout()
        fig.savefig(staging / "preview.png", format="png")
        plt.close(fig)
        (staging / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = {"schema_version": "1", "audit": audit, "files": {"preview": sha256_file(staging / "preview.png"), "audit": sha256_file(staging / "audit.json")}}
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return output, audit
