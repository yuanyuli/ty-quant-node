import pandas as pd
from ty_quant_node.engine import train_predict, backtest, save_report

def fixture():
    rows=[]
    for i,d in enumerate(pd.date_range("2024-01-01", periods=6)):
        for ins,base in [("AAA",10+i),("BBB",20-i*0.2)]:
            rows.append(dict(datetime=d,instrument=ins,open_raw=base,high_raw=base+1,low_raw=base-1,close_raw=base,volume_raw=1000,adj_factor=1 if i<3 else 2))
    return pd.DataFrame(rows)

def test_end_to_end():
    result=train_predict(fixture(),"qfq"); metrics,curve=backtest(result,1)
    assert len(result["data"]) > 0
    assert len(curve) > 0 and "total_return" in metrics


def test_compat_report_publishes_atomic_directory(tmp_path):
    result = train_predict(fixture(), "qfq")
    metrics, curve = backtest(result, 1)

    output = save_report(metrics, curve, tmp_path / "report")

    assert (tmp_path / "report" / "metrics.json").exists()
    assert output == str((tmp_path / "report").resolve())
