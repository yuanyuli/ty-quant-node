import pandas as pd
import pytest

from ty_quant_node.backend.backtest_backend import backtest


def test_backtest_empty_signal_has_null_risk_metrics():
    result = backtest(pd.DataFrame(columns=["instrument", "datetime", "score", "label"]), topk=1)
    assert result.metrics["days"] == 0
    assert result.metrics["sharpe"] is None
    assert result.metrics["ic"] is None


def test_backtest_single_day_has_no_sharpe():
    signal = pd.DataFrame([{"instrument": "AAA", "datetime": "2024-01-01", "score": 1.0, "label": 0.02}])
    result = backtest(signal, topk=1)
    assert result.metrics["days"] == 1
    assert result.metrics["total_return"] == pytest.approx(0.02)
    assert result.metrics["sharpe"] is None


def test_backtest_drops_nonfinite_signal_values():
    signal = pd.DataFrame([
        {"instrument": "AAA", "datetime": "2024-01-01", "score": float("nan"), "label": 0.02},
        {"instrument": "BBB", "datetime": "2024-01-01", "score": 1.0, "label": float("nan")},
    ])
    result = backtest(signal, topk=1)
    assert result.metrics["days"] == 0
