import pandas as pd
from ty_quant_node.data import apply_adjustment

def test_qfq_preserves_raw_and_adjusts_price_volume():
    df=pd.DataFrame({"instrument":["SH600000"]*2,"datetime":pd.to_datetime(["2024-01-01","2024-01-02"]),"open_raw":[10.,5.],"high_raw":[11.,6.],"low_raw":[9.,4.],"close_raw":[10.,5.],"volume_raw":[100.,200.],"adj_factor":[1.,2.]})
    out=apply_adjustment(df,"qfq")
    assert out.close_raw.tolist()==[10.,5.]
    assert out.close.tolist()==[5.,5.]
    assert out.volume.tolist()==[200.,200.]
    assert out.factor.tolist()==[0.5, 1.0]


def test_none_adjustment_uses_identity_qlib_factor():
    df = pd.DataFrame({
        "instrument": ["SH600000"],
        "datetime": pd.to_datetime(["2024-01-01"]),
        "open_raw": [10.0], "high_raw": [11.0], "low_raw": [9.0],
        "close_raw": [10.0], "volume_raw": [100.0], "adj_factor": [3.0],
    })
    out = apply_adjustment(df, "none")
    assert out.factor.tolist() == [1.0]

def test_missing_factor_is_rejected():
    df=pd.DataFrame({"close_raw":[1.],"adj_factor":[None]})
    try: apply_adjustment(df,"qfq")
    except ValueError as e: assert "复权因子" in str(e)
    else: raise AssertionError("expected ValueError")
