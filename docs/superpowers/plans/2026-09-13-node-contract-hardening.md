# 节点输入契约与中文界面实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `QlibControl` 在工作流入口就拒绝不合理的量化配置，并让 ComfyUI 注册信息显示稳定的中文产品名称，同时保持现有字段名、句柄类型和旧工作流兼容。

**Architecture:** 在 `nodes.py` 增加纯校验辅助函数，集中校验枚举、数值范围、日期成对关系、Tushare 查询区间和 JSON 结构；`QlibControl.run` 只保存规范化后的值，不访问外部文件。注册表使用显式 `NODE_DISPLAY_NAME_MAPPINGS`，避免默认英文类名直接暴露给 ComfyUI。

**Tech Stack:** Python 3.10+, pandas, `math`, pytest, ComfyUI object info contract。

**Spec:** `docs/specs/2026-09-12-qlib-comfyui-mvp-design.md`、`docs/specs/2026-09-13-ty-factors-data-nodes-design.md` 和 README 的 QlibControl 总控约定。

## Global Constraints

- 节点仓库固定为 `D:\work_station\ty-comfyui-node\ty-quant-node`，运行时不依赖 `ty-quant`。
- 不改变已有输入字段英文 key、RETURN_TYPES、句柄 kind 和工作流 JSON 结构。
- 控制节点只做参数校验和 metadata 构造，不读取 token、不访问网络、不要求 CSV 已存在。
- 所有错误使用中文消息，包含具体字段名和修复方向；路径安全仍由下游 `resolve_node_path` 执行。
- 测试使用固定 fixture，不修改 ComfyUI 内置 Python 环境。

### Task 1: 总控参数早期校验

**Files:**
- Modify: `src/ty_quant_node/nodes.py`（增加校验 helper，修改 `QlibControl.run`）
- Test: `tests/test_control_node.py`

**Interfaces:**
- `QlibControl.run(...) -> tuple[dict]` 保持不变。
- 非法枚举、空输出目录、区间不完整、Tushare 日期反转、`n_drop > topk`、非有限交易成本和错误 JSON 在总控节点抛出 `ValueError` 或现有 `RuntimeError`。

- [ ] **Step 1: 写失败测试**

```python
def test_control_rejects_invalid_strategy_parameters(tmp_path):
    with pytest.raises(ValueError, match="n_drop"):
        _control(tmp_path, topk=1, n_drop=2)
    with pytest.raises(ValueError, match="交易成本"):
        _control(tmp_path, transaction_cost_bps=float("nan"))


def test_control_rejects_invalid_tushare_window(tmp_path):
    with pytest.raises(ValueError, match="start_date"):
        _control(tmp_path, csv_path="", ts_codes="000001.SZ", start_date="20240102", end_date="20240101")
```

- [ ] **Step 2: 运行测试确认失败**

运行：`uv run pytest ty-quant-node/tests/test_control_node.py::test_control_rejects_invalid_strategy_parameters ty-quant-node/tests/test_control_node.py::test_control_rejects_invalid_tushare_window -q`

预期：失败，因为当前总控只保存值，不校验 `n_drop`、有限交易成本和 Tushare 日期关系。

- [ ] **Step 3: 实现最小校验**

新增 `_validate_control_inputs(...)`：

```python
if str(adjustment) not in {"qfq", "hfq", "none"}:
    raise ValueError("adjustment 必须是 qfq、hfq 或 none")
if int(topk) < 1 or int(n_drop) < 0 or int(n_drop) > int(topk):
    raise ValueError("n_drop 必须在 0 到 topk 之间")
if not math.isfinite(float(transaction_cost_bps)) or float(transaction_cost_bps) < 0:
    raise ValueError("交易成本必须是非负有限数")
```

同时校验 `model_type`、`segment`、`adjustment_policy`、`factor_set` 枚举；`artifact_dir`、`report_dir`、`output_root` 非空；训练/测试日期复用 `_validate_date_range_inputs`；Tushare `start_date/end_date` 成对填写且可由 `pandas.Timestamp` 解析、开始不晚于结束；`selected_json` 必须是字符串数组，`custom_json` 必须是对象或数组。保留原始日期字符串和路径字符串写入 metadata。

- [ ] **Step 4: 运行聚焦测试确认通过**

运行：`uv run pytest ty-quant-node/tests/test_control_node.py -q`

预期：原有控制扇出测试与新增非法参数测试全部通过。

- [ ] **Step 5: 提交**

```bash
git add src/ty_quant_node/nodes.py tests/test_control_node.py
git commit -m "feat: validate qlib control inputs early"
```

### Task 2: 中文 ComfyUI 注册名称

**Files:**
- Modify: `src/ty_quant_node/nodes.py:NODE_DISPLAY_NAME_MAPPINGS`
- Test: `tests/test_registration_contract.py`

**Interfaces:**
- `NODE_CLASS_MAPPINGS` key 保持原样。
- `NODE_DISPLAY_NAME_MAPPINGS` 为每个公开节点提供稳定中文名称，`/object_info/<node>` 的 `display_name` 不再是英文类名。

- [ ] **Step 1: 写失败测试**

```python
def test_registered_nodes_expose_chinese_display_names():
    module = importlib.import_module("ty_quant_node")
    assert module.NODE_DISPLAY_NAME_MAPPINGS["QlibControl"] == "TY Quant 总控"
    assert module.NODE_DISPLAY_NAME_MAPPINGS["QlibPredict"] == "TY Quant 预测"
```

- [ ] **Step 2: 运行测试确认失败**

运行：`uv run pytest ty-quant-node/tests/test_registration_contract.py::test_registered_nodes_expose_chinese_display_names -q`

预期：失败，因为当前映射是 `{key: key}`。

- [ ] **Step 3: 实现显式映射**

为 14 个公开节点写完整字典：总控、Qlib 运行时、Tushare 配置/同步/转换、TY-Factors、复权、Qlib 导出/Dataset/模型/训练/预测/回测/报告均使用稳定中文名称；不要修改 `NODE_CLASS_MAPPINGS`。

- [ ] **Step 4: 运行测试确认通过**

运行：`uv run pytest ty-quant-node/tests/test_registration_contract.py ty-quant-node/tests/test_node_contracts.py -q`

预期：注册契约与输出名称测试全部通过。

- [ ] **Step 5: 提交**

```bash
git add src/ty_quant_node/nodes.py tests/test_registration_contract.py
git commit -m "feat: add chinese comfyui display names"
```

### Task 3: 文档、ComfyUI object info 与全量门禁

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Test: 全量 `tests/`

- [ ] **Step 1: 更新文档**

说明 QlibControl 会在入口校验策略参数和日期窗口，列出 `n_drop <= topk`、非负有限交易成本、Tushare 日期成对规则；说明 ComfyUI 搜索列表使用中文显示名但 workflow key 不变。

- [ ] **Step 2: 重启独立 ComfyUI 并检查 object info**

重启 `8190` 进程后调用 `GET /object_info/QlibControl` 和 `GET /object_info/QlibPredict`，确认 `display_name` 分别为 `TY Quant 总控`、`TY Quant 预测`，输入 key 与旧工作流一致。

- [ ] **Step 3: 运行完整门禁**

```powershell
uv run pytest ty-quant-node/tests -q
uv lock --check
uv run python -m compileall ty-quant-node/src
git diff --check
git status --short --branch
```

预期：测试零失败、锁文件和编译通过、工作区只含本阶段提交。

- [ ] **Step 4: 提交并推送**

```bash
git add src/ty_quant_node/nodes.py tests/test_registration_contract.py tests/test_control_node.py README.md CHANGELOG.md docs/superpowers/plans/2026-09-13-node-contract-hardening.md
git commit -m "feat: harden node contracts and chinese ui"
git push origin master
```

## 自审清单

- Spec coverage：Task 1 覆盖总控参数契约，Task 2 覆盖 ComfyUI 显示注册，Task 3 覆盖文档和真实 object info 验证。
- Placeholder scan：每个步骤均有具体文件、代码或命令，无 TBD/TODO。
- Type consistency：映射只改变 display name，不改变节点 key；校验只在 `QlibControl` 输入边界执行，句柄返回类型不变。
