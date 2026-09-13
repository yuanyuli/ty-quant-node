from ty_quant_node.workflow import build_mvp_workflow, validate_workflow, workflow_to_prompt


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
