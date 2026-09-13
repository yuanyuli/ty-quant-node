"""Tushare Pro 日线和复权因子适配器。"""

import json
import os
import time
import hashlib
import re
from urllib.request import Request, urlopen
import pandas as pd


class _Secret(str):
    def __repr__(self):
        return "<redacted>"


class TushareError(RuntimeError):
    pass


class TushareDailySource:
    def __init__(
        self,
        token: str | None = None,
        *,
        token_env_name: str = "TUSHARE_TOKEN",
        transport=None,
        retries: int = 3,
        sleep=time.sleep,
        timeout_seconds: float = 30.0,
    ):
        token_env_name = str(token_env_name or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token_env_name):
            raise ValueError("Tushare token_env_name 必须是合法环境变量名")
        self._token_env_name = token_env_name
        self._token = token or os.getenv(token_env_name)
        if not self._token:
            raise ValueError(f"未找到 {token_env_name}")
        self._transport = transport or self._http_transport
        self._retries = max(1, int(retries))
        self._sleep = sleep
        self._timeout_seconds = max(1.0, float(timeout_seconds))

    def _http_transport(self, payload):
        request = Request(
            "http://api.tushare.pro",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self._timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _call(self, api_name: str, params: dict):
        payload = {"api_name": api_name, "token": _Secret(self._token), "params": params, "fields": ""}
        for attempt in range(self._retries):
            try:
                response = self._transport(payload)
                break
            except (OSError, TimeoutError) as exc:
                if attempt + 1 >= self._retries:
                    raise TushareError(f"Tushare 网络请求失败: {type(exc).__name__}") from exc
                self._sleep(0.2 * (attempt + 1))
        if response.get("code", 0) != 0:
            message = str(response.get("msg") or "未知错误")
            if "token" in message.lower() or "权限" in message or "认证" in message:
                raise TushareError("Tushare 认证或权限错误，请检查会员权限和 TUSHARE_TOKEN")
            raise TushareError(f"Tushare 接口错误: {message}")
        data = response.get("data") or {}
        fields, items = data.get("fields") or [], data.get("items") or []
        return pd.DataFrame(items, columns=fields)

    def fetch(self, ts_codes: list[str], start_date: str, end_date: str, *, include_events: bool = False) -> pd.DataFrame:
        if not ts_codes:
            raise ValueError("至少提供一个股票代码")
        codes = [str(code).strip().upper() for code in ts_codes if str(code).strip()]
        if not codes:
            raise ValueError("至少提供一个股票代码")
        start = self._normalize_date(start_date, "start_date")
        end = self._normalize_date(end_date, "end_date")
        if start > end:
            raise ValueError("start_date 不能晚于 end_date")
        params = {"ts_code": ",".join(codes), "start_date": start, "end_date": end}
        daily = self._call("daily", params)
        factor = self._call("adj_factor", params)
        if daily.empty:
            raise TushareError("Tushare 日线接口无数据")
        daily = daily.rename(
            columns={
                "ts_code": "instrument",
                "trade_date": "datetime",
                "open": "open_raw",
                "high": "high_raw",
                "low": "low_raw",
                "close": "close_raw",
                "vol": "volume_raw",
                "amount": "amount_raw",
            }
        )
        factor = factor.rename(columns={"ts_code": "instrument", "trade_date": "datetime"})
        keep = ["instrument", "datetime", "adj_factor"]
        merged = daily.merge(factor[keep], on=["instrument", "datetime"], how="left", validate="many_to_one")
        merged["datetime"] = pd.to_datetime(merged["datetime"].astype(str))
        merged["trade_status"] = 1
        merged["source"] = "tushare"
        merged["asof"] = pd.Timestamp.now(tz="UTC").isoformat()
        if include_events:
            events = self._call("dividend", params)
            merged.attrs["events"] = self._normalize_events(events, merged)
        return merged.sort_values(["datetime", "instrument"]).reset_index(drop=True)

    @staticmethod
    def _normalize_date(value: str, field: str) -> str:
        try:
            parsed = pd.Timestamp(str(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} 日期无效") from exc
        if pd.isna(parsed):
            raise ValueError(f"{field} 日期无效")
        return parsed.strftime("%Y%m%d")

    @staticmethod
    def _normalize_events(events: pd.DataFrame, daily: pd.DataFrame | None = None) -> list[dict]:
        if events is None or events.empty:
            return []
        columns = set(events.columns)
        if {"instrument", "effective_date", "price_multiplier", "split_multiplier"}.issubset(columns):
            return events.to_dict("records")
        if not {"ts_code", "ex_date", "stk_div"}.issubset(columns):
            raise TushareError("Tushare 分红接口缺少 ex_date/stk_div，无法构造 PIT 事件")
        factor_lookup: dict[tuple[str, pd.Timestamp], float] = {}
        if daily is not None and {"instrument", "datetime", "adj_factor"}.issubset(daily.columns):
            factor_frame = daily[["instrument", "datetime", "adj_factor"]].copy()
            factor_frame["instrument"] = factor_frame["instrument"].astype(str).str.upper()
            factor_frame["datetime"] = pd.to_datetime(factor_frame["datetime"]).dt.normalize()
            factor_lookup = {
                (str(row.instrument), pd.Timestamp(row.datetime)): float(row.adj_factor)
                for row in factor_frame.itertuples(index=False)
                if pd.notna(row.adj_factor) and float(row.adj_factor) > 0
            }
        factor_history: dict[str, list[tuple[pd.Timestamp, float]]] = {}
        if daily is not None and factor_lookup:
            for row in daily.sort_values(["instrument", "datetime"]).itertuples(index=False):
                if pd.notna(row.adj_factor) and float(row.adj_factor) > 0:
                    factor_history.setdefault(str(row.instrument).upper(), []).append(
                        (pd.Timestamp(row.datetime).normalize(), float(row.adj_factor))
                    )
        result = []
        for _, row in events.iterrows():
            if pd.isna(row.get("ex_date")):
                continue
            stock_div = float(row.get("stk_div") or 0.0)
            # Tushare stk_div 是每股送转比例，例如 10 送 2 表示 0.2。
            split_multiplier = 1.0 + stock_div
            instrument = str(row["ts_code"]).upper()
            effective = pd.Timestamp(row["ex_date"]).normalize()
            knowledge_raw = row.get("ann_date")
            if pd.isna(knowledge_raw):
                knowledge_raw = row["ex_date"]
            price_multiplier = split_multiplier
            current_factor = factor_lookup.get((instrument, effective))
            if current_factor is not None:
                history = [item for item in factor_history.get(instrument, []) if item[0] < effective]
                previous = history[-1] if history else None
                if previous is not None and previous[1] > 0:
                    price_multiplier = current_factor / previous[1]
            result.append(
                {
                    "instrument": instrument,
                    "effective_date": effective,
                    "knowledge_date": pd.Timestamp(knowledge_raw).normalize(),
                    "price_multiplier": price_multiplier,
                    "split_multiplier": split_multiplier,
                    "event_source": "tushare_dividend",
                }
            )
        return result

    @staticmethod
    def snapshot_id(frame: pd.DataFrame, events: list[dict] | None = None) -> str:
        stable = frame.drop(columns=["asof"], errors="ignore")
        payload = stable.sort_values(["instrument", "datetime"]).to_json(date_format="iso", orient="records")
        event_payload = json.dumps(events or [], ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256((payload + event_payload).encode("utf-8")).hexdigest()[:24]
