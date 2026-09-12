"""轻量 TopK/Dropout 日频回测。"""

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    metrics: dict
    equity: pd.DataFrame
    signal: pd.DataFrame


def _metrics(curve: pd.DataFrame, daily_returns: pd.Series, trades: int, signal: pd.DataFrame, initial_equity: float) -> dict:
    if curve.empty:
        return {"total_return": 0.0, "annualized_return": None, "max_drawdown": 0.0, "sharpe": None, "ic": None, "rank_ic": None, "trades": 0, "days": 0}
    equity = curve["equity"]
    normalized_final = float(equity.iloc[-1] / initial_equity)
    total_return = normalized_final - 1.0
    annualized = float(normalized_final ** (252 / len(curve)) - 1.0) if normalized_final > 0 else None
    drawdown = equity / equity.cummax() - 1.0
    sharpe = float(np.sqrt(252) * daily_returns.mean() / daily_returns.std(ddof=1)) if len(daily_returns) > 1 and daily_returns.std(ddof=1) > 0 else None
    ic_values = signal.groupby("datetime").apply(lambda g: g["score"].corr(g["label"]) if len(g) >= 2 else np.nan, include_groups=False).dropna()
    rank_values = signal.groupby("datetime").apply(lambda g: g["score"].rank().corr(g["label"].rank()) if len(g) >= 2 else np.nan, include_groups=False).dropna()
    return {"total_return": total_return, "annualized_return": annualized, "max_drawdown": float(drawdown.min()), "sharpe": sharpe, "ic": float(ic_values.mean()) if not ic_values.empty else None, "rank_ic": float(rank_values.mean()) if not rank_values.empty else None, "trades": int(trades), "days": int(len(curve))}


def backtest(signal: pd.DataFrame, market_frame: pd.DataFrame | None = None, *, topk=1, n_drop=0, transaction_cost_bps=0.0, initial_equity=1.0) -> BacktestResult:
    if topk < 1:
        raise ValueError("topk 必须大于等于 1")
    required = {"instrument", "datetime", "score"}
    if not required.issubset(signal.columns):
        raise ValueError(f"信号缺少字段: {', '.join(sorted(required - set(signal.columns)))}")
    table = signal.copy()
    table["datetime"] = pd.to_datetime(table["datetime"])
    if "label" not in table and market_frame is not None:
        market = market_frame.copy()
        if "close" not in market and "close_raw" in market:
            from ..data import apply_adjustment

            market = apply_adjustment(market, "none")
        market["datetime"] = pd.to_datetime(market["datetime"])
        market["label"] = market.groupby("instrument")["close"].shift(-1) / market["close"] - 1.0
        table = table.merge(market[["instrument", "datetime", "label"]], on=["instrument", "datetime"], how="left")
    if "label" not in table:
        table["label"] = np.nan
    table = table.replace([np.inf, -np.inf], np.nan).dropna(subset=["score", "label"])
    rows, previous, equity = [], set(), float(initial_equity)
    for dt, group in table.groupby("datetime", sort=True):
        group = group.sort_values("score", ascending=False)
        selected = list(group.head(topk)["instrument"])
        if previous and n_drop < topk:
            keep = [instrument for instrument in previous if instrument in set(group["instrument"])][: max(0, topk - n_drop)]
            selected = keep + [instrument for instrument in selected if instrument not in keep][: max(0, topk - len(keep))]
        picks = group[group["instrument"].isin(selected)].head(topk)
        gross_return = float(picks["label"].mean()) if not picks.empty else 0.0
        turnover = len(set(selected) - previous) + len(previous - set(selected))
        net_return = gross_return - (turnover / max(topk, 1)) * transaction_cost_bps / 10000.0
        equity *= 1.0 + net_return
        rows.append({"datetime": dt, "return": net_return, "equity": equity, "turnover": turnover})
        previous = set(selected)
    curve = pd.DataFrame(rows, columns=["datetime", "return", "equity", "turnover"])
    metrics = _metrics(curve, curve["return"] if not curve.empty else pd.Series(dtype=float), int(curve["turnover"].sum()) if not curve.empty else 0, table, float(initial_equity))
    return BacktestResult(metrics, curve, table)
