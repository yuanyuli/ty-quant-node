from ty_quant_node.workflow import build_mvp_workflow, build_ty_factors_workflow, validate_workflow, workflow_to_prompt


def test_legacy_workflow_is_rejected_for_editor_metadata():
    workflow = {
        "last_node_id": 1,
        "last_link_id": 0,
        "nodes": [
            {
                "id": 1,
                "type": "QlibReport",
                "inputs": [{"name": "backtest_result", "type": "QLIB_BACKTEST_RESULT", "link": None}],
                "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": None}],
                "widgets_values": ["outputs/report"],
            }
        ],
        "links": [],
    }

    errors = validate_workflow(workflow)

    assert any("version" in error for error in errors)
    assert any("QlibReport" in error and "输出" in error for error in errors)


def test_generated_workflow_has_control_fanout_and_complete_ports(tmp_path):
    workflow = build_mvp_workflow(str(tmp_path / "market.csv"), str(tmp_path / "artifacts"))

    assert validate_workflow(workflow) == []
    assert workflow["version"] == 0.4
    assert len(workflow["groups"]) == 4
    assert {node["type"] for node in workflow["nodes"]} == {
        "QlibControl",
        "QlibExport",
        "QlibDataset",
        "QlibModel",
        "QlibTrain",
        "QlibPredict",
        "QlibBacktest",
        "QlibReport",
    }
    report = next(node for node in workflow["nodes"] if node["type"] == "QlibReport")
    assert [output["type"] for output in report["outputs"]] == ["STRING", "IMAGE", "STRING"]
    assert report["widgets_values_named"]["output_dir"].endswith("artifacts\\report") or report["widgets_values_named"]["output_dir"].endswith("artifacts/report")
    assert sum(link[1] == 1 for link in workflow["links"]) == 7


def test_workflow_to_prompt_preserves_widget_and_link_values(tmp_path):
    workflow = build_mvp_workflow(str(tmp_path / "market.csv"), str(tmp_path / "artifacts"))

    prompt = workflow_to_prompt(workflow)

    assert prompt["1"]["class_type"] == "QlibControl"
    assert prompt["1"]["inputs"]["csv_path"].endswith("market.csv")
    assert prompt["2"]["inputs"]["control"] == ["1", 0]
    assert prompt["5"]["inputs"]["model"] == ["4", 0]


def test_ty_factors_workflow_has_valid_links_and_api_contract(tmp_path):
    workflow = build_ty_factors_workflow("000001.SZ", "2024-01-01", "2024-12-31", str(tmp_path / "artifacts"))

    assert validate_workflow(workflow) == []
    prompt = workflow_to_prompt(workflow)
    assert len(prompt) == 11
    assert prompt["1"]["class_type"] == "QlibControl"
    assert prompt["2"]["class_type"] == "TushareConfig"
    assert prompt["3"]["inputs"]["control"] == ["1", 0]
    assert prompt["4"]["inputs"]["control"] == ["1", 0]
    assert prompt["5"]["inputs"]["control"] == ["1", 0]
    assert prompt["6"]["inputs"]["control"] == ["1", 0]
    assert prompt["7"]["inputs"]["control"] == ["1", 0]
    assert prompt["8"]["inputs"]["control"] == ["1", 0]
    assert prompt["9"]["inputs"]["control"] == ["1", 0]
    assert prompt["10"]["inputs"]["control"] == ["1", 0]
    assert prompt["11"]["inputs"]["control"] == ["1", 0]
    assert prompt["8"]["inputs"]["model"] == ["7", 0]
    assert prompt["9"]["inputs"]["dataset"] == ["6", 0]
    assert prompt["10"]["inputs"]["signal"] == ["9", 0]
    assert prompt["11"]["inputs"]["backtest_result"] == ["10", 0]
    assert prompt["5"]["inputs"]["output_dir"].endswith("artifacts\\factors") or prompt["5"]["inputs"]["output_dir"].endswith("artifacts/factors")
    assert prompt["11"]["inputs"]["output_dir"].endswith("artifacts\\report") or prompt["11"]["inputs"]["output_dir"].endswith("artifacts/report")
    assert prompt["1"]["inputs"]["ts_codes"] == "000001.SZ"
    assert prompt["1"]["inputs"]["adjustment_policy"] == "pit"
