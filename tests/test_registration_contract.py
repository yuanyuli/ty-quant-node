import importlib
import numpy as np
import random
import sys
import types
import pytest
from ty_quant_node.nodes import QlibControl, QlibRuntime, QlibReport


def test_comfyui_root_registers_full_node_group():
    module = importlib.import_module("ty_quant_node")
    expected = {
        "TushareConfig",
        "QlibControl",
        "QlibRuntime",
        "TushareDailyFetch",
        "TushareToQlib",
        "TYFactorCompute",
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
    assert module.WEB_DIRECTORY.endswith("web")


def test_runtime_node_initializes_qlib(tmp_path):
    handle = QlibRuntime().run(str(tmp_path), "cn", 42, str(tmp_path / "experiments"))[0]
    assert handle["kind"] == "QLIB_RUNTIME"
    assert handle["metadata"]["seed"] == 42
    assert handle["metadata"]["experiment_uri"].endswith("experiments")


def test_runtime_returns_compat_handle_without_qlib(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "qlib", None)
    handle = QlibRuntime().run(str(tmp_path), "cn", 7, "")[0]
    assert handle["metadata"]["qlib_version"] == "unavailable"
    assert handle["metadata"]["dataset_backend"] == "compat"
    assert handle["path"] == str(tmp_path.resolve())


def test_runtime_seeds_compat_backend(monkeypatch, tmp_path):
    calls = {"python": [], "numpy": []}
    monkeypatch.setattr(random, "seed", lambda value: calls["python"].append(value))
    monkeypatch.setattr(np.random, "seed", lambda value: calls["numpy"].append(value))
    monkeypatch.setitem(sys.modules, "qlib", None)

    QlibRuntime().run(str(tmp_path), "cn", 17, "")

    assert calls == {"python": [17], "numpy": [17]}


def test_runtime_wraps_qlib_initialization_error(monkeypatch, tmp_path):
    def fail_init(**_kwargs):
        raise ValueError("provider 配置无效")

    monkeypatch.setitem(sys.modules, "qlib", types.SimpleNamespace(init=fail_init))

    with pytest.raises(RuntimeError, match="QlibRuntime 初始化失败"):
        QlibRuntime().run(str(tmp_path), "cn", 42, "")


def test_report_is_comfyui_output_node():
    assert QlibReport.OUTPUT_NODE is True


def test_control_node_is_registered_with_optional_fanout_contract():
    assert "QLIB_CONTROL" in QlibControl.RETURN_TYPES
    assert QlibControl.INPUT_TYPES()["required"]["csv_path"][0] == "STRING"


def test_registered_nodes_expose_chinese_display_names():
    module = importlib.import_module("ty_quant_node")

    assert module.NODE_DISPLAY_NAME_MAPPINGS["QlibControl"] == "TY Quant 总控"
    assert module.NODE_DISPLAY_NAME_MAPPINGS["QlibPredict"] == "TY Quant 预测"
