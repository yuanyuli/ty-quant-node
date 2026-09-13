import json
from pathlib import Path

from ty_quant_node.workflow import validate_workflow, workflow_to_prompt


def test_checked_in_workflow_is_editor_valid_and_api_ready():
    path = Path(__file__).parents[1] / "examples" / "mvp_workflow.json"
    workflow = json.loads(path.read_text(encoding="utf-8"))

    assert validate_workflow(workflow) == []
    prompt = workflow_to_prompt(workflow)
    assert len(prompt) == 8
    assert prompt["1"]["class_type"] == "QlibControl"
    assert prompt["8"]["class_type"] == "QlibReport"
    assert prompt["8"]["inputs"]["backtest_result"] == ["7", 0]
    assert Path(prompt["1"]["inputs"]["csv_path"]).name == "market.csv"
