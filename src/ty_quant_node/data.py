import pandas as pd

def apply_adjustment(df: pd.DataFrame, adjustment: str = "qfq") -> pd.DataFrame:
    if adjustment not in {"none", "qfq", "hfq"}: raise ValueError("不支持的复权方式")
    out=df.copy()
    if adjustment == "none":
        out["close"]=out["close_raw"]; out["open"]=out["open_raw"]; out["high"]=out["high_raw"]; out["low"]=out["low_raw"]; out["volume"]=out["volume_raw"]; return out
    if out["adj_factor"].isna().any() or (out["adj_factor"]<=0).any(): raise ValueError("复权因子缺失或非正")
    anchor=float(out.sort_values("datetime")["adj_factor"].iloc[-1])
    ratio=out["adj_factor"].astype(float)/anchor if adjustment=="qfq" else out["adj_factor"].astype(float)
    for c in ("open","high","low","close"): out[c]=out[f"{c}_raw"]*ratio
    out["volume"]=out["volume_raw"]/ratio
    out.attrs["adjustment_anchor_factor"]=anchor
    return out
