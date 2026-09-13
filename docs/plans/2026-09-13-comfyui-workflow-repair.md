# Qlib ComfyUI 工作台工作流修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成一个符合 ComfyUI 0.4 编辑器格式、采用 H3 导演工作台式布局、可以在真实 ComfyUI 中执行并产出回测报告的 ty-quant-node MVP 工作流。

**Architecture:** 新增 `QlibControl` 总控节点，只负责集中保存数据源、复权、时间切分、模型和回测配置，输出版本化 `QLIB_CONTROL` 句柄。现有阶段节点通过可选 control 输入读取对应配置，计算仍由原来的导出、Dataset、模型、预测、回测和报告模块完成。工作流由 Python builder 生成，使用节点真实 `INPUT_TYPES`/`RETURN_TYPES` 构造端口，并由结构校验器检查编辑器元数据、链接双向一致性和实际端口数量。

**Tech Stack:** Python 3.12、ComfyUI custom nodes、pytest、PowerShell、现有 Qlib 兼容后端和固定 CSV fixture。

**Spec:** `docs/specs/2026-09-12-qlib-comfyui-mvp-design.md` 及本次已确认的 H3 风格模块化工作台设计。

## Global Constraints

- 节点仓库必须独立维护在 `D:\work_station\ty-comfyui-node\ty-quant-node`。
- 不修改 ComfyUI 内置 Python 环境；只通过 junction 接入节点仓库。
- Tushare token 不进入 workflow、日志或 artifact。
- 工作流不得保存行情表、模型二进制或回测大表，只保存配置和链接。
- 所有用户文档、测试说明和注释使用中文；代码公共字段使用英文。
- 最终工作流必须复制到 `E:\ComfyUI_windows_portable-G314\ComfyUI\user\default\workflows\ty-qlib`。

---

### Task 1: 建立总控句柄和节点覆盖测试

**Files:**
- Modify: `src/ty_quant_node/core/handles.py`
- Modify: `src/ty_quant_node/nodes.py`
- Create: `tests/test_control_node.py`
- Modify: `tests/test_registration_contract.py`

**Interfaces:**
- `QlibControl.run(...) -> tuple[dict]` 返回 `QLIB_CONTROL` 句柄。
- 各阶段节点新增可选 `control` 输入；未连接时保持现有参数行为。

- [x] **Step 1: Write the failing test**

增加测试，断言 `QLIB_CONTROL` 可往返、`QlibControl` 注册，并且 `QlibExport` 能从 control 覆盖 CSV、复权和输出目录。

- [x] **Step 2: Run test to verify it fails**

运行 `uv run pytest ty-quant-node/tests/test_control_node.py ty-quant-node/tests/test_registration_contract.py -q`，预期因为未知句柄类型和缺少节点而失败。

- [x] **Step 3: Write minimal implementation**

在 `Handle.KNOWN_KINDS` 中加入 `QLIB_CONTROL`；实现总控节点和 `_control_values` 解析；为导出、Dataset、Model、Train、Predict、Backtest、Report 增加可选覆盖。

- [x] **Step 4: Run test to verify it passes**

重复运行上述测试，确认总控和覆盖行为通过。

- [x] **Step 5: Commit**

提交 `feat: add qlib control node`。

### Task 2: 工作流 builder 与结构校验

**Files:**
- Create: `src/ty_quant_node/workflow.py`
- Create: `tests/test_workflow_schema.py`
- Modify: `src/ty_quant_node/__init__.py`

**Interfaces:**
- `build_mvp_workflow(csv_path: str, artifact_root: str) -> dict` 生成完整 ComfyUI 0.4 workflow。
- `validate_workflow(workflow: dict) -> list[str]` 返回结构错误，空列表表示通过。

- [x] **Step 1: Write the failing test**

测试要求顶层有 `id/revision/version/config/extra/groups`，节点端口数量匹配真实注册节点，所有 link 同时出现在来源 output 和目标 input，且 `QlibReport` 的 IMAGE 位于真实第二输出槽。

- [x] **Step 2: Run test to verify it fails**

运行 `uv run pytest ty-quant-node/tests/test_workflow_schema.py -q`，预期当前 `examples/mvp_workflow.json` 缺少编辑器元数据并出现端口不一致。

- [x] **Step 3: Write minimal implementation**

实现节点序列化、widget 输入标记、输出槽位、H3 风格分组和稳定链接 ID；校验器从 `NODE_CLASS_MAPPINGS` 的 `INPUT_TYPES` 与 `RETURN_TYPES` 获取真实端口定义。

- [x] **Step 4: Run test to verify it passes**

用 builder 生成 JSON 后运行 schema 测试。

- [x] **Step 5: Commit**

提交 `feat: generate valid comfyui workflow`。

### Task 3: 生成并安装 H3 风格 MVP 工作流

**Files:**
- Modify: `examples/mvp_workflow.json`
- Modify: `README.md`
- Modify: `docs/plans/2026-09-12-qlib-comfyui-mvp.md`
- Create: `examples/README.md`

**Interfaces:**
- 工作流包含 `QlibControl -> QlibExport -> QlibDataset -> QlibModel -> QlibTrain -> QlibPredict -> QlibBacktest -> QlibReport` 主链。
- `QlibControl` 的配置扇出到各阶段；报告同时输出摘要字符串和图片。

- [x] **Step 1: Write the failing test**

在 schema 测试中要求工作流包含总控节点、四个分组标题和目标文件可被 JSON 解析。

- [x] **Step 2: Run test to verify it fails**

运行 `uv run pytest ty-quant-node/tests/test_workflow_schema.py -q`，确认旧工作流没有总控节点和分组。

- [x] **Step 3: Write minimal implementation**

调用 builder 生成固定 fixture 工作流，使用本机仓库的绝对 fixture 路径和 `.artifacts/comfyui-mvp` 输出路径，避免 ComfyUI 当前工作目录导致输入找不到。

- [x] **Step 4: Run test to verify it passes**

解析并校验 `examples/mvp_workflow.json`，确认所有节点、链接和配置字段正确。

- [x] **Step 5: Commit**

提交 `docs: document comfyui workbench workflow`。

### Task 4: 独立执行和真实 ComfyUI 联调

**Files:**
- Modify: `tests/test_node_workflow.py`
- Create: `tests/test_comfyui_workflow_payload.py`
- External copy: `E:\ComfyUI_windows_portable-G314\ComfyUI\user\default\workflows\ty-qlib\mvp_workflow.json`

**Interfaces:**
- 独立测试验证 controller 覆盖后的完整节点链和报告图片。
- ComfyUI API 验证 workflow 转换成 prompt 后执行成功；前端工作流文件验证版本、节点和 link 数量。

- [x] **Step 1: Write the failing test**

增加测试检查 workflow 中的所有 widget 路径存在、节点真实注册、输出报告路径可预期。

- [x] **Step 2: Run test to verify it fails**

先运行独立测试和 payload 检查，记录旧工作流的缺失项。

- [x] **Step 3: Write minimal implementation**

修正路径和测试 fixture；复制生成的 workflow 到 ComfyUI 用户工作流目录，重启后端并确认 `/object_info` 和 `/prompt` 执行。

- [x] **Step 4: Run test to verify it passes**

运行全量 `uv run pytest ty-quant-node/tests -q`；调用本地 ComfyUI API，轮询 history，确认 `status_str=success`、报告 PNG、metrics JSON 和 equity CSV 均生成。

- [x] **Step 5: Commit**

提交 `test: verify comfyui workflow end to end`，然后推送 GitHub。
