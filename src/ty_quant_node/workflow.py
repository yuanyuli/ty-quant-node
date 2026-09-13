"""生成和校验可被 ComfyUI 编辑器加载的 Qlib 工作流。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import uuid

from .nodes import NODE_CLASS_MAPPINGS


EDITOR_FIELDS = {
    "id",
    "revision",
    "last_node_id",
    "last_link_id",
    "nodes",
    "links",
    "groups",
    "config",
    "extra",
    "version",
}
PRIMITIVE_TYPES = {"STRING", "INT", "FLOAT", "BOOLEAN", "COMBO"}


def _type_name(spec: tuple[Any, ...]) -> str:
    raw = spec[0]
    return "COMBO" if isinstance(raw, list) else str(raw)


def _is_widget(spec: tuple[Any, ...]) -> bool:
    raw = spec[0]
    return isinstance(raw, list) or str(raw) in PRIMITIVE_TYPES


def _default_value(spec: tuple[Any, ...]) -> Any:
    raw = spec[0]
    options = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    if "default" in options:
        return options["default"]
    if isinstance(raw, list):
        return raw[0] if raw else None
    return None


def _input_specs(node_type: str) -> list[tuple[str, tuple[Any, ...]]]:
    cls = NODE_CLASS_MAPPINGS[node_type]
    definitions = cls.INPUT_TYPES()
    result: list[tuple[str, tuple[Any, ...]]] = []
    for section in ("required", "optional"):
        result.extend((name, spec) for name, spec in definitions.get(section, {}).items())
    return result


def _output_types(node_type: str) -> tuple[str, ...]:
    return tuple(str(value) for value in NODE_CLASS_MAPPINGS[node_type].RETURN_TYPES)


def _make_node(
    node_id: int,
    node_type: str,
    values: dict[str, Any],
    links_by_input: dict[str, int],
    links_by_output: dict[int, list[int]],
    *,
    position: tuple[int, int],
    size: tuple[int, int],
    order: int,
    title: str,
    color: str,
    bgcolor: str,
) -> dict[str, Any]:
    inputs: list[dict[str, Any]] = []
    widget_values: list[Any] = []
    widgets_values_named: dict[str, Any] = {}
    for name, spec in _input_specs(node_type):
        input_data: dict[str, Any] = {"name": name, "type": _type_name(spec)}
        link = links_by_input.get(name)
        input_data["link"] = link
        if link is not None:
            input_data["shape"] = 7
        if _is_widget(spec):
            input_data["widget"] = {"name": name}
            value = values.get(name, _default_value(spec))
            widget_values.append(value)
            widgets_values_named[name] = value
        inputs.append(input_data)

    outputs = []
    for slot, output_type in enumerate(_output_types(node_type)):
        output_links = links_by_output.get(slot, [])
        outputs.append(
            {
                "name": output_type,
                "type": output_type,
                "slot_index": slot,
                "links": output_links or None,
            }
        )

    return {
        "id": node_id,
        "type": node_type,
        "pos": list(position),
        "size": list(size),
        "flags": {"pinned": True},
        "order": order,
        "mode": 0,
        "inputs": inputs,
        "outputs": outputs,
        "title": title,
        "properties": {
            "cnr_id": "ty-quant-node",
            "ver": "0.1.0",
            "Node name for S&R": node_type,
        },
        "widgets_values": widget_values,
        "widgets_values_named": widgets_values_named,
        "color": color,
        "bgcolor": bgcolor,
    }


def _link(link_id: int, source: tuple[int, int], target: tuple[int, int], link_type: str) -> list[Any]:
    return [link_id, source[0], source[1], target[0], target[1], link_type]


def build_mvp_workflow(csv_path: str, artifact_root: str) -> dict[str, Any]:
    """构造带总控节点的 Qlib MVP 编辑器工作流。"""

    csv = str(Path(csv_path).resolve())
    root = Path(artifact_root).resolve()
    values = {
        "csv_path": csv,
        "adjustment": "qfq",
        "output_root": str(root / "provider"),
        "train_start": "2024-01-01",
        "train_end": "2024-01-03",
        "test_start": "2024-01-04",
        "test_end": "2024-01-06",
        "model_type": "linear",
        "params_json": "{}",
        "artifact_dir": str(root / "model"),
        "segment": "test",
        "topk": 1,
        "n_drop": 0,
        "transaction_cost_bps": 5.0,
        "report_dir": str(root / "report"),
    }

    # Link 1-7 are the H3-style control fan-out; link 8-14 are the data path.
    links = [
        _link(1, (1, 0), (2, 3), "QLIB_CONTROL"),
        _link(2, (1, 0), (3, 5), "QLIB_CONTROL"),
        _link(3, (1, 0), (4, 2), "QLIB_CONTROL"),
        _link(4, (1, 0), (5, 3), "QLIB_CONTROL"),
        _link(5, (1, 0), (6, 3), "QLIB_CONTROL"),
        _link(6, (1, 0), (7, 4), "QLIB_CONTROL"),
        _link(7, (1, 0), (8, 2), "QLIB_CONTROL"),
        _link(8, (2, 0), (3, 0), "QLIB_EXPORT"),
        _link(9, (3, 0), (5, 0), "QLIB_DATASET"),
        _link(10, (4, 0), (5, 1), "QLIB_MODEL_SPEC"),
        _link(11, (5, 0), (6, 0), "QLIB_TRAINED_MODEL"),
        _link(12, (3, 0), (6, 1), "QLIB_DATASET"),
        _link(13, (6, 0), (7, 0), "QLIB_SIGNAL_TABLE"),
        _link(14, (7, 0), (8, 0), "QLIB_BACKTEST_RESULT"),
    ]
    links_by_input = {
        (2, "control"): 1,
        (3, "control"): 2,
        (4, "control"): 3,
        (5, "control"): 4,
        (6, "control"): 5,
        (7, "control"): 6,
        (8, "control"): 7,
        (3, "export"): 8,
        (5, "dataset"): 9,
        (5, "model"): 10,
        (6, "trained_model"): 11,
        (6, "dataset"): 12,
        (7, "signal"): 13,
        (8, "backtest_result"): 14,
    }
    links_by_output = {
        1: {0: [1, 2, 3, 4, 5, 6, 7]},
        2: {0: [8]},
        3: {0: [9, 12]},
        4: {0: [10]},
        5: {0: [11]},
        6: {0: [13]},
        7: {0: [14]},
    }
    specs = [
        (1, "QlibControl", (0, 0), (520, 760), 0, "TY Quant 控制台", "#16727c", "#4f0074"),
        (2, "QlibExport", (640, 70), (420, 220), 1, "数据导出与复权", "#356b8c", "#254b63"),
        (3, "QlibDataset", (1140, 70), (420, 260), 2, "Dataset 时间切分", "#356b8c", "#254b63"),
        (4, "QlibModel", (640, 390), (420, 190), 1, "模型配置", "#6d5a35", "#4d3f26"),
        (5, "QlibTrain", (1640, 70), (420, 260), 3, "模型训练", "#6d5a35", "#4d3f26"),
        (6, "QlibPredict", (2140, 70), (420, 220), 4, "信号预测", "#6d5a35", "#4d3f26"),
        (7, "QlibBacktest", (2640, 70), (440, 260), 5, "TopK 回测", "#794c36", "#593827"),
        (8, "QlibReport", (3160, 70), (440, 300), 6, "回测报告", "#794c36", "#593827"),
    ]
    nodes = []
    for node_id, node_type, position, size, order, title, color, bgcolor in specs:
        node_input_links = {name: link_id for (target_id, name), link_id in links_by_input.items() if target_id == node_id}
        node_values = dict(values)
        if node_type == "QlibExport":
            node_values["output_dir"] = str(root / "provider")
        elif node_type == "QlibReport":
            node_values["output_dir"] = str(root / "report")
        nodes.append(
            _make_node(
                node_id,
                node_type,
                node_values,
                node_input_links,
                links_by_output.get(node_id, {}),
                position=position,
                size=size,
                order=order,
                title=title,
                color=color,
                bgcolor=bgcolor,
            )
        )

    return {
        "id": str(uuid.UUID("5d91bce2-2dd4-4b64-9d1c-25bda1d0c001")),
        "revision": 0,
        "last_node_id": 8,
        "last_link_id": 14,
        "nodes": nodes,
        "links": links,
        "groups": [
            {"title": "TY Quant 控制台", "bounding": [-20, -20, 580, 820], "color": "#3f789e", "font_size": 24},
            {"title": "数据准备与复权", "bounding": [610, 20, 1000, 640], "color": "#3f789e", "font_size": 24},
            {"title": "模型训练与预测", "bounding": [1610, 20, 1000, 640], "color": "#7f704b", "font_size": 24},
            {"title": "回测与报告", "bounding": [2610, 20, 1040, 640], "color": "#8c573b", "font_size": 24},
        ],
        "config": {},
        "extra": {
            "workflow_name": "TY Quant Qlib MVP",
            "description": "H3 导演工作台式的 Qlib 日线复权、训练、预测、回测和报告闭环。",
        },
        "version": 0.4,
    }


def validate_workflow(workflow: dict[str, Any]) -> list[str]:
    """检查工作流是否能被编辑器恢复为与节点定义一致的图。"""

    errors: list[str] = []
    missing = EDITOR_FIELDS - set(workflow)
    errors.extend(f"缺少顶层字段: {field}" for field in sorted(missing))
    if workflow.get("version") != 0.4:
        errors.append("version 必须是 0.4")
    if not isinstance(workflow.get("groups"), list) or not workflow.get("groups"):
        errors.append("groups 不能为空")

    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return errors + ["nodes 必须是数组"]
    node_by_id: dict[int, dict[str, Any]] = {}
    for node in nodes:
        node_id = node.get("id")
        node_type = node.get("type")
        if node_id in node_by_id:
            errors.append(f"节点 ID 重复: {node_id}")
        node_by_id[node_id] = node
        required_fields = {"id", "type", "pos", "size", "flags", "order", "mode", "inputs", "outputs", "properties", "widgets_values"}
        errors.extend(f"节点 {node_type} 缺少字段: {field}" for field in sorted(required_fields - set(node)))
        if node_type not in NODE_CLASS_MAPPINGS:
            errors.append(f"未知节点类型: {node_type}")
            continue
        expected_inputs = _input_specs(node_type)
        actual_inputs = node.get("inputs", [])
        expected_names = [name for name, _ in expected_inputs]
        actual_names = [item.get("name") for item in actual_inputs]
        if actual_names != expected_names:
            errors.append(f"{node_type} 输入端口不匹配: 期望 {expected_names}, 实际 {actual_names}")
        expected_outputs = _output_types(node_type)
        actual_outputs = node.get("outputs", [])
        if len(actual_outputs) != len(expected_outputs):
            errors.append(f"{node_type} 输出数量不匹配: 期望 {len(expected_outputs)}, 实际 {len(actual_outputs)}")
        for index, expected_type in enumerate(expected_outputs):
            if index >= len(actual_outputs):
                break
            if actual_outputs[index].get("type") != expected_type:
                errors.append(f"{node_type} 输出 {index} 类型不匹配: 期望 {expected_type}")

    links = workflow.get("links")
    if not isinstance(links, list):
        return errors + ["links 必须是数组"]
    link_ids: set[int] = set()
    for record in links:
        if not isinstance(record, list) or len(record) != 6:
            errors.append(f"链接格式错误: {record}")
            continue
        link_id, source_id, source_slot, target_id, target_slot, link_type = record
        if link_id in link_ids:
            errors.append(f"链接 ID 重复: {link_id}")
        link_ids.add(link_id)
        source = node_by_id.get(source_id)
        target = node_by_id.get(target_id)
        if source is None or target is None:
            errors.append(f"链接 {link_id} 引用了不存在的节点")
            continue
        source_outputs = source.get("outputs", [])
        target_inputs = target.get("inputs", [])
        if source_slot >= len(source_outputs) or link_id not in (source_outputs[source_slot].get("links") or []):
            errors.append(f"链接 {link_id} 未出现在来源输出槽")
        if target_slot >= len(target_inputs) or target_inputs[target_slot].get("link") != link_id:
            errors.append(f"链接 {link_id} 未出现在目标输入槽")
        if source_slot < len(source_outputs) and source_outputs[source_slot].get("type") != link_type:
            errors.append(f"链接 {link_id} 类型与来源输出不一致")
    return errors


def workflow_to_prompt(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """把编辑器 workflow 转成 ComfyUI `/prompt` API 所需的节点字典。"""

    links = {record[0]: record for record in workflow.get("links", [])}
    prompt: dict[str, dict[str, Any]] = {}
    for node in workflow.get("nodes", []):
        inputs: dict[str, Any] = {}
        named_values = node.get("widgets_values_named", {})
        for input_data in node.get("inputs", []):
            name = input_data["name"]
            link_id = input_data.get("link")
            if link_id is not None:
                record = links[link_id]
                inputs[name] = [str(record[1]), record[2]]
            elif "widget" in input_data and name in named_values:
                inputs[name] = named_values[name]
        prompt[str(node["id"])] = {"class_type": node["type"], "inputs": inputs}
    return prompt
