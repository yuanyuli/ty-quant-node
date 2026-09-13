import pytest

from ty_quant_node.nodes import QlibExport, TushareConfig, TushareDailyFetch, TushareToQlib, TYFactorCompute


def test_tushare_fetch_outputs_market_data_and_conversion_outputs_qlib_export():
    assert TushareDailyFetch.RETURN_TYPES == ("MARKET_DATA",)
    assert TushareToQlib.RETURN_TYPES == ("QLIB_EXPORT",)
    assert TYFactorCompute.RETURN_TYPES == ("QLIB_FEATURE_SET", "STRING")
    assert TushareDailyFetch.INPUT_TYPES()["required"]["snapshot_dir"][0] == "STRING"
    assert TushareToQlib.INPUT_TYPES()["required"]["market_data"][0] == "MARKET_DATA"


def test_factor_compute_exposes_explicit_factor_set_modes():
    modes = TYFactorCompute.INPUT_TYPES()["required"]["factor_set"][0]
    assert modes == ["ty_factors", "alpha158", "selected", "custom"]


def test_tushare_config_exposes_environment_name_without_accepting_raw_token():
    required = TushareConfig.INPUT_TYPES()["required"]
    assert required["token_source"][0] == ["environment"]
    assert required["token_env_name"][1]["default"] == "TUSHARE_TOKEN"
    assert "token" not in required


def test_node_outputs_have_stable_display_names():
    assert TushareDailyFetch.RETURN_NAMES == ("行情快照",)
    assert TushareToQlib.RETURN_NAMES == ("Qlib 数据",)
    assert TYFactorCompute.RETURN_NAMES == ("因子特征", "摘要")


def test_qlib_export_rejects_remote_csv_before_reader_runs(tmp_path):
    with pytest.raises(ValueError, match="本地文件路径"):
        QlibExport().run("https://example.com/market.csv", "qfq", str(tmp_path / "provider"))
