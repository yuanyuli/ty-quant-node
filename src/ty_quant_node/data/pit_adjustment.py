"""按事件生效日构造不使用未来信息的复权序列。"""

from __future__ import annotations

from collections.abc import Iterable
import math

import pandas as pd


REQUIRED_MARKET_FIELDS = {
    "instrument",
    "datetime",
    "open_raw",
    "high_raw",
    "low_raw",
    "close_raw",
    "volume_raw",
}
REQUIRED_EVENT_FIELDS = {"instrument", "effective_date", "price_multiplier", "split_multiplier"}


def derive_vendor_events(frame: pd.DataFrame) -> list[dict]:
    """从供应商按日期返回的累计 factor 推导事件增量。

    这是 vendor snapshot 的降级路径：它能阻止未来日期的 factor 直接回写过去，
    但不能替代带公告日期的真实 corporate action 事件，因此 manifest 必须标记
    为非严格 PIT。
    """
    if "adj_factor" not in frame:
        return []
    working = frame[["instrument", "datetime", "adj_factor"]].copy()
    working["instrument"] = working["instrument"].astype(str).str.strip().str.upper()
    working["datetime"] = pd.to_datetime(working["datetime"], errors="coerce").dt.normalize()
    working["adj_factor"] = pd.to_numeric(working["adj_factor"], errors="coerce")
    if working["adj_factor"].isna().any() or (working["adj_factor"] <= 0).any():
        raise ValueError("供应商 adj_factor 必须为正数")
    events: list[dict] = []
    for instrument, group in working.sort_values(["instrument", "datetime"]).groupby("instrument", sort=False):
        previous = None
        for _, row in group.iterrows():
            current = float(row["adj_factor"])
            if previous is not None:
                multiplier = current / previous
                if not math.isclose(multiplier, 1.0, rel_tol=1e-9, abs_tol=1e-9):
                    events.append(
                        {
                            "instrument": instrument,
                            "effective_date": row["datetime"],
                            "knowledge_date": row["datetime"],
                            "price_multiplier": multiplier,
                            "split_multiplier": multiplier,
                            "event_source": "vendor_adj_factor",
                        }
                    )
            previous = current
    return events


def _as_events(events: Iterable[dict] | pd.DataFrame | None) -> pd.DataFrame:
    if events is None:
        return pd.DataFrame(columns=sorted(REQUIRED_EVENT_FIELDS))
    result = events.copy() if isinstance(events, pd.DataFrame) else pd.DataFrame(list(events))
    if result.empty:
        return pd.DataFrame(columns=sorted(REQUIRED_EVENT_FIELDS))
    missing = REQUIRED_EVENT_FIELDS - set(result.columns)
    if missing:
        raise ValueError(f"复权事件缺少字段: {', '.join(sorted(missing))}")
    result = result.copy()
    result["instrument"] = result["instrument"].astype(str).str.strip().str.upper()
    result["effective_date"] = pd.to_datetime(result["effective_date"], errors="coerce").dt.normalize()
    if "knowledge_date" not in result:
        result["knowledge_date"] = result["effective_date"]
    result["knowledge_date"] = pd.to_datetime(result["knowledge_date"], errors="coerce").dt.normalize()
    for field in ("price_multiplier", "split_multiplier"):
        result[field] = pd.to_numeric(result[field], errors="coerce")
        if result[field].isna().any() or (result[field] <= 0).any():
            raise ValueError(f"复权事件 {field} 必须为正数")
    if result["effective_date"].isna().any() or result["knowledge_date"].isna().any():
        raise ValueError("复权事件日期无效")
    if result.duplicated(["instrument", "effective_date"]).any():
        raise ValueError("同一标的同一生效日存在重复复权事件")
    # 事件只有在生效日和已知日都到达后才能进入序列。按激活日排序，
    # 避免一个晚到事件阻塞后面已经可用的事件。
    result["_activation_date"] = result[["effective_date", "knowledge_date"]].max(axis=1)
    return result.sort_values(["instrument", "_activation_date", "effective_date"]).reset_index(drop=True)


def build_pit_adjustment(
    frame: pd.DataFrame,
    events: Iterable[dict] | pd.DataFrame | None,
    *,
    snapshot_id: str,
) -> pd.DataFrame:
    """构建只使用当日已知事件的价格、成交量和 factor。

    `price_multiplier` 作用于 OHLC 和总收益价格，`split_multiplier` 只作用于
    成交量。事件不会影响其 effective_date 之前的行；后续同步应通过新的
    snapshot_id 生成新版本，而不是覆盖旧结果。
    """
    missing = REQUIRED_MARKET_FIELDS - set(frame.columns)
    if missing:
        raise ValueError(f"行情数据缺少字段: {', '.join(sorted(missing))}")
    if not snapshot_id:
        raise ValueError("snapshot_id 不能为空")

    out = frame.copy()
    out["instrument"] = out["instrument"].astype(str).str.strip().str.upper()
    out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce").dt.normalize()
    if out["datetime"].isna().any():
        raise ValueError("行情日期无效")
    for field in REQUIRED_MARKET_FIELDS - {"instrument", "datetime"}:
        out[field] = pd.to_numeric(out[field], errors="coerce")
    if out.duplicated(["instrument", "datetime"]).any():
        raise ValueError("同一标的同一日期存在重复行情")

    event_frame = _as_events(events)
    event_map = {
        instrument: group.to_dict("records")
        for instrument, group in event_frame.groupby("instrument", sort=False)
    }
    rows: list[pd.DataFrame] = []
    for instrument, group in out.sort_values(["instrument", "datetime"]).groupby("instrument", sort=False):
        price_factor = 1.0
        split_factor = 1.0
        event_index = 0
        instrument_events = event_map.get(instrument, [])
        computed = []
        for _, row in group.iterrows():
            current_date = row["datetime"]
            while event_index < len(instrument_events):
                event = instrument_events[event_index]
                if event["_activation_date"] > current_date:
                    break
                price_factor *= float(event["price_multiplier"])
                split_factor *= float(event["split_multiplier"])
                event_index += 1
            if not math.isfinite(price_factor) or not math.isfinite(split_factor):
                raise ValueError(f"{instrument} PIT 复权因子溢出")
            item = row.to_dict()
            item.update(
                {
                    "ty_price_factor": price_factor,
                    "ty_split_factor": split_factor,
                    "factor": price_factor,
                    "ty_open": float(row["open_raw"]) * price_factor,
                    "ty_high": float(row["high_raw"]) * price_factor,
                    "ty_low": float(row["low_raw"]) * price_factor,
                    "ty_close": float(row["close_raw"]) * price_factor,
                    "ty_volume": float(row["volume_raw"]) / split_factor,
                }
            )
            if "amount_raw" in row.index:
                item["amount"] = row["amount_raw"]
                item["ty_vwap"] = float(row["amount_raw"]) / float(row["volume_raw"]) * price_factor if float(row["volume_raw"]) else float("nan")
            computed.append(item)
        rows.append(pd.DataFrame(computed))

    result = pd.concat(rows, ignore_index=True).sort_values(["datetime", "instrument"]).reset_index(drop=True)
    result.attrs.update(
        {
            "adjustment": "pit",
            "factor_definition": "ty_price_adjusted/original",
            "snapshot_id": snapshot_id,
            "point_in_time": True,
        }
    )
    return result
