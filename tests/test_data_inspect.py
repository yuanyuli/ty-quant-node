import json

import pandas as pd

from ty_quant_node.backend.market import export_qlib
from ty_quant_node.nodes import TYDataInspect


def test_data_inspect_generates_kline_and_quality_report(tmp_path, market_frame, monkeypatch):
    monkeypatch.setenv("TY_QUANT_ALLOWED_ROOTS", str(tmp_path))
    csv = tmp_path / "market.csv"
    market_frame.to_csv(csv, index=False)
    export = export_qlib(market_frame, tmp_path / "provider", adjustment="qfq")

    image, summary, raw_result, audit = TYDataInspect().run(
        market_data=None,
        qlib_export=export,
        instrument="AAA",
        lookback=5,
        output_dir=str(tmp_path / "inspect"),
    )

    assert audit["kind"] == "DATA_AUDIT"
    assert audit["metadata"]["instrument"] == "AAA"
    assert audit["metadata"]["rows"] == 5
    assert audit["metadata"]["duplicate_count"] == 0
    assert "AAA" in summary
    assert '"instrument": "AAA"' in raw_result
    assert (tmp_path / "inspect" / "preview.png").exists()
    assert image.ndim == 4
