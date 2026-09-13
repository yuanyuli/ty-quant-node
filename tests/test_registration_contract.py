import importlib
from ty_quant_node.nodes import QlibControl, QlibRuntime, QlibReport


def test_comfyui_root_registers_full_node_group():
    module = importlib.import_module("ty_quant_node")
    expected = {
        "TushareConfig",
        "QlibControl",
        "QlibRuntime",
        "TushareDailyFetch",
        "AdjustPrices",
        "QlibExport",
        "QlibDataset",
        "QlibModel",
        "QlibTrain",
        "QlibPredict",
        "QlibBacktest",
        "QlibReport",
    }
    assert expected.issubset(module.NODE_CLASS_MAPPINGS)
    for name in expected:
        assert module.NODE_CLASS_MAPPINGS[name].INPUT_TYPES()["required"]


def test_runtime_node_initializes_qlib(tmp_path):
    handle = QlibRuntime().run(str(tmp_path), "cn", 42, str(tmp_path / "experiments"))[0]
    assert handle["kind"] == "QLIB_RUNTIME"
    assert handle["metadata"]["seed"] == 42
    assert handle["metadata"]["experiment_uri"].endswith("experiments")


def test_report_is_comfyui_output_node():
    assert QlibReport.OUTPUT_NODE is True


def test_control_node_is_registered_with_optional_fanout_contract():
    assert "QLIB_CONTROL" in QlibControl.RETURN_TYPES
    assert QlibControl.INPUT_TYPES()["required"]["csv_path"][0] == "STRING"
