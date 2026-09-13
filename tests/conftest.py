import os
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def allow_test_artifacts(monkeypatch, tmp_path):
    """把每个测试的临时目录加入节点白名单，模拟用户显式配置。"""

    configured = [str(tmp_path)]
    existing = os.getenv("TY_QUANT_ALLOWED_ROOTS")
    if existing:
        configured.append(existing)
    configured.append(str(Path.cwd()))
    monkeypatch.setenv("TY_QUANT_ALLOWED_ROOTS", os.pathsep.join(configured))


@pytest.fixture
def market_frame():
    rows = []
    for i, dt in enumerate(pd.date_range("2024-01-01", periods=6)):
        for instrument, base in (("AAA", 10 + i), ("BBB", 20 - i * 0.2)):
            rows.append(
                {
                    "datetime": dt,
                    "instrument": instrument,
                    "open_raw": base,
                    "high_raw": base + 1,
                    "low_raw": base - 1,
                    "close_raw": base,
                    "volume_raw": 1000.0,
                    "amount_raw": base * 1000,
                    "adj_factor": 1.0 if i < 3 else 2.0,
                    "trade_status": 1,
                }
            )
    return pd.DataFrame(rows)
