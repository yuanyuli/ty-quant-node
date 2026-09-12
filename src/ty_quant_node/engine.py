"""离线可测试的 Qlib MVP 引擎。"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from qlib.data.dataset.loader import StaticDataLoader
from .data import apply_adjustment

def build_dataset(raw: pd.DataFrame, adjustment="qfq"):
    df = apply_adjustment(raw, adjustment)
    df = df.sort_values(["datetime", "instrument"]).copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["feature_return"] = df.groupby("instrument")["close"].pct_change().fillna(0.0)
    df["label"] = df.groupby("instrument")["close"].shift(-1) / df["close"] - 1.0
    df = df.dropna(subset=["label"])
    qdf = df.set_index(["datetime", "instrument"])[["feature_return", "label"]]
    loader = StaticDataLoader(qdf)
    # StaticDataLoader 是 Qlib 官方 Dataset loader；MVP 直接保留 loader，
    # 后续接入 Handler 时可无缝替换为 DatasetH。
    return loader, df

def train_predict(raw: pd.DataFrame, adjustment="qfq"):
    dataset, derived = build_dataset(raw, adjustment)
    x = derived[["feature_return"]].to_numpy(float); y = derived["label"].to_numpy(float)
    X = np.c_[np.ones(len(x)), x]
    coef = np.linalg.lstsq(X, y, rcond=None)[0]
    derived["prediction"] = np.c_[np.ones(len(x)), x] @ coef
    return {"dataset": dataset, "data": derived, "coef": coef.tolist(), "adjustment": adjustment}

def backtest(result, topk=1, initial_cash=1_000_000.0):
    df = result["data"].copy(); rows=[]; equity=initial_cash
    for dt, g in df.groupby("datetime"):
        picks=g.nlargest(topk, "prediction"); ret=float(picks["label"].mean()) if len(picks) else 0.0
        equity *= 1.0 + ret; rows.append({"datetime": dt, "return": ret, "equity": equity})
    curve=pd.DataFrame(rows); metrics={"total_return": float(equity/initial_cash-1), "final_equity": float(equity), "days": len(curve)}
    return metrics, curve

def save_report(metrics, curve, output_dir):
    out=Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    (out/"metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    curve.to_csv(out/"equity.csv", index=False)
    return str(out)
