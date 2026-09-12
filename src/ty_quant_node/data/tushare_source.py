"""Tushare Pro 日线和复权因子适配器。"""

import json
import os
import time
from urllib.request import Request, urlopen
import pandas as pd


class _Secret(str):
    def __repr__(self):
        return "<redacted>"


class TushareError(RuntimeError):
    pass


class TushareDailySource:
    def __init__(self, token: str | None = None, *, transport=None, retries: int = 3, sleep=time.sleep):
        self._token = token or os.getenv("TUSHARE_TOKEN")
        if not self._token:
            raise ValueError("未找到 TUSHARE_TOKEN")
        self._transport = transport or self._http_transport
        self._retries = max(1, int(retries))
        self._sleep = sleep

    @staticmethod
    def _http_transport(payload):
        request = Request(
            "http://api.tushare.pro",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
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

    def fetch(self, ts_codes: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        if not ts_codes:
            raise ValueError("至少提供一个股票代码")
        params = {"ts_code": ",".join(ts_codes), "start_date": start_date, "end_date": end_date}
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
        return merged.sort_values(["datetime", "instrument"]).reset_index(drop=True)
