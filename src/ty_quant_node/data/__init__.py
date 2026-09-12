"""行情数据规范化与复权。"""

import pandas as pd


def apply_adjustment(
    df: pd.DataFrame,
    adjustment: str = "qfq",
    *,
    allow_unadjusted: bool = False,
) -> pd.DataFrame:
    if adjustment not in {"none", "qfq", "hfq"}:
        raise ValueError("不支持的复权方式")
    if adjustment in {"qfq", "hfq"} and "adj_factor" not in df:
        raise ValueError("复权因子缺失或非正")
    if adjustment in {"qfq", "hfq"} and "adj_factor" in df:
        factor_check = pd.to_numeric(df["adj_factor"], errors="coerce")
        if factor_check.isna().any() or (factor_check <= 0).any():
            raise ValueError("复权因子缺失或非正")
    required = {"datetime", "instrument", "open_raw", "high_raw", "low_raw", "close_raw", "volume_raw"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"行情数据缺少字段: {', '.join(sorted(missing))}")
    out = df.copy()
    out["datetime"] = pd.to_datetime(out["datetime"])
    out = out.sort_values(["datetime", "instrument"]).reset_index(drop=True)
    for field in ("open_raw", "high_raw", "low_raw", "close_raw", "volume_raw"):
        out[field] = pd.to_numeric(out[field], errors="coerce")
    if adjustment == "none":
        for field in ("open", "high", "low", "close", "volume"):
            out[field] = out[f"{field}_raw"]
        if "amount_raw" in out:
            out["amount"] = out["amount_raw"]
        out.attrs["adjustment"] = "none"
        return out
    if "adj_factor" not in out:
        out["adj_factor"] = 1.0
    factors = pd.to_numeric(out["adj_factor"], errors="coerce")
    invalid = factors.isna() | (factors <= 0)
    if invalid.any() and not allow_unadjusted:
        raise ValueError("复权因子缺失或非正")
    factors = factors.mask(invalid, 1.0)
    valid_rows = out.loc[~invalid, ["datetime", "adj_factor"]]
    if valid_rows.empty:
        raise ValueError("复权因子缺失或非正")
    anchor_row = valid_rows.sort_values("datetime").iloc[-1]
    anchor = float(anchor_row["adj_factor"])
    ratio = factors / anchor if adjustment == "qfq" else factors
    for field in ("open", "high", "low", "close"):
        out[field] = out[f"{field}_raw"] * ratio
    out["volume"] = out["volume_raw"] / ratio
    if "amount_raw" in out:
        out["amount"] = out["amount_raw"]
    out.attrs.update(
        {
            "adjustment": adjustment,
            "adjustment_anchor_factor": anchor,
            "adjustment_anchor_date": pd.Timestamp(anchor_row["datetime"]).isoformat(),
            "quality_errors": int(invalid.sum()),
        }
    )
    return out
