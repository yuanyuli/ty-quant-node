import pandas as pd
import pytest


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
