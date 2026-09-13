# QlibControl 总控节点交互重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `QlibControl` 重构为数据源明确、参数分区、日期和路径控件适配研究流程的 ComfyUI 总控节点，并让新版 Tushare/CSV MVP 工作流可执行。

**Architecture:** Python 节点定义提供 schema v2 字段、中文 tooltip 和统一产物根目录；后端注册白名单目录浏览 API；前端扩展只增强 `QlibControl` 的布局、条件显示、路径选择和日期输入。旧字段与旧示例直接删除后重新生成，数据计算模块通过新的 control metadata 读取配置。

**Tech Stack:** Python 3.10+、pandas、aiohttp/ComfyUI PromptServer routes、ComfyUI LiteGraph extension、pytest、固定 fixture 和 8190 联调实例。

**Spec:** `docs/superpowers/specs/2026-09-13-qlib-control-ux-design.md`

## Global Constraints

- 所有 Qlib 节点相关内容继续位于 `D:\work_station\ty-comfyui-node\ty-quant-node` 独立仓库。
- 本版直接升级配置契约，不保留旧工作流兼容；旧字段和旧示例按 schema v2 重建。
- token 不进入 workflow、日志、目录 API 响应、句柄 metadata 或 artifact。
- 目录 API 只能访问 `configured_allowed_roots()` 返回的白名单，后端节点执行仍调用 `resolve_node_path()`。
- 下游 artifact 完整性、PIT 复权和因子计算算法保持不变。

## 文件结构

- Modify `src/ty_quant_node/nodes.py`: QlibControl schema v2、校验和下游控制字段读取。
- Create `src/ty_quant_node/fs_routes.py`: ComfyUI 白名单目录/文件浏览路由。
- Modify `__init__.py` and `src/ty_quant_node/__init__.py`: 注册路由和 `WEB_DIRECTORY`。
- Create `web/ty_quant_control.js`: 区域标题、条件显示、日期控件、路径选择器。
- Modify `src/ty_quant_node/workflow.py`: 新字段 builder、validator、prompt 转换。
- Replace `examples/mvp_workflow.json` and `examples/ty_factors_workflow.json`: schema v2 工作流。
- Modify `tests/test_control_node.py`, `tests/test_workflow_schema.py`, `tests/test_registration_contract.py`: 新契约与校验。
- Create `tests/test_fs_routes.py`: 路由白名单和目录响应测试。
- Modify `tests/test_comfyui_workflow_payload.py`: 新工作流 API payload 测试。
- Modify `README.md` and `CHANGELOG.md`: 新总控配置和交互说明。

### Task 1: 重写 QlibControl schema v2 和 metadata

**Files:**
- Modify: `src/ty_quant_node/nodes.py` 的 `_validate_control_inputs`、`QlibControl.INPUT_TYPES`、`QlibControl.run`。
- Modify: `tests/test_control_node.py`、`tests/test_registration_contract.py`。

**Interfaces:**
- `QlibControl.run(data_source, csv_path, ts_codes, query_start, query_end, adjustment_mode, include_events, incremental, train_start, train_end, test_start, test_end, factor_set, selected_json, custom_json, model_type, params_json, segment, topk, n_drop, transaction_cost_bps, artifact_root) -> tuple[dict]`。
- metadata 必须包含 `config_schema_version="2"`、新字段和派生目录 `provider_dir/snapshot_dir/factor_dir/model_dir/report_dir`。

- [ ] **Step 1: 写失败测试**：断言新 `INPUT_TYPES` 只有 schema v2 字段、每个 widget 有中文 tooltip；断言 `artifact_root` 派生五个目录；断言旧 `output_root/adjustment_policy/report_dir` 不再出现。
- [ ] **Step 2: 运行 `uv run pytest ty-quant-node/tests/test_control_node.py ty-quant-node/tests/test_registration_contract.py -q`，确认新测试失败。**
- [ ] **Step 3: 实现 schema v2 输入定义、中文 tooltip、统一日期和产物目录派生；删除旧字段读取和旧回退分支。**
- [ ] **Step 4: 运行同一测试命令，确认通过，并运行现有 control 校验测试确认 n_drop、交易成本、日期和 JSON 校验仍有效。**
- [ ] **Step 5: 提交 `feat: redesign qlib control schema`。**

### Task 2: 更新下游节点读取新 control metadata

**Files:**
- Modify: `src/ty_quant_node/nodes.py` 中 `TushareDailyFetch`、`TushareToQlib`、`TYFactorCompute`、`QlibExport`、`QlibDataset`、`QlibModel`、`QlibTrain`、`QlibPredict`、`QlibBacktest`、`QlibReport` 的 control 读取处。
- Modify: `tests/test_tushare_nodes.py`、`tests/test_node_workflow.py`。

**Interfaces:**
- `_controlled(values, key, fallback)` 继续按新字段读取；路径节点使用 `provider_dir/snapshot_dir/factor_dir/model_dir/report_dir`；复权节点使用 `adjustment_mode`。

- [ ] **Step 1: 写失败测试**：使用 schema v2 control 运行本地 CSV 和 Tushare fake workflow，断言下游不再读取旧键，并且五个派生目录被使用。
- [ ] **Step 2: 运行对应测试，确认旧 metadata 导致失败。**
- [ ] **Step 3: 实现新字段映射并删除旧字段分支；保持节点输出类型不变。**
- [ ] **Step 4: 运行 `uv run pytest ty-quant-node/tests/test_tushare_nodes.py ty-quant-node/tests/test_node_workflow.py -q`。**
- [ ] **Step 5: 提交 `refactor: consume schema v2 control metadata`。**

### Task 3: 增加安全目录浏览 API

**Files:**
- Create: `src/ty_quant_node/fs_routes.py`。
- Modify: `__init__.py`、`src/ty_quant_node/__init__.py`。
- Create: `tests/test_fs_routes.py`。

**Interfaces:**
- `register_routes()`：在 ComfyUI 可用时注册 `GET /ty-quant-node/fs/roots` 和 `GET /ty-quant-node/fs/list`；无 ComfyUI 环境导入时安全跳过。
- `/roots` 返回 `{roots: [{path, label}]}`；`/list` 返回 `{current, parent, entries:[{name,path,is_dir,is_file,extension}]}`。

- [ ] **Step 1: 写失败测试**：对临时白名单根目录断言 roots/list 返回目录和 CSV/Parquet；对 `..`、URL、白名单外路径断言 400/403；响应不包含 token 字段。
- [ ] **Step 2: 运行 `uv run pytest ty-quant-node/tests/test_fs_routes.py -q`，确认失败。**
- [ ] **Step 3: 实现路由，所有路径先用 `resolve_allowed_path` 校验；只读列目录，不创建、删除或读取文件内容。**
- [ ] **Step 4: 运行路由测试，并做源码编译检查。**
- [ ] **Step 5: 提交 `feat: add safe filesystem browsing routes`。**

### Task 4: 实现 QlibControl 前端交互扩展

**Files:**
- Create: `web/ty_quant_control.js`。
- Modify: `__init__.py` 增加 `WEB_DIRECTORY = "./web"`。

**Interfaces:**
- `app.registerExtension({name:"ty-quant-node.control", beforeRegisterNodeDef})` 只增强 `QlibControl`。
- 扩展识别 widget 名称：`data_source`、`csv_path`、`ts_codes`、`query_start/query_end`、`train_start/train_end`、`test_start/test_end`、`artifact_root`。

- [ ] **Step 1: 写静态契约测试**：检查 JS 注册扩展名称、六个区域标题、两个路由 URL、日期 input 类型和 data_source 条件隐藏逻辑。
- [ ] **Step 2: 运行静态测试，确认缺少 JS 时失败。**
- [ ] **Step 3: 实现区域标题和分隔线，使用 DOM widget 保持 LiteGraph 序列化值为字符串。**
- [ ] **Step 4: 实现 CSV/目录按钮和安全浏览 modal：roots → list，取消不改值，选择回填路径。**
- [ ] **Step 5: 实现三组日期范围 widget，日历选择、键盘输入、清空和前端顺序提示。**
- [ ] **Step 6: 运行静态测试并在 8190 浏览器中刷新节点，确认布局和交互。**
- [ ] **Step 7: 提交 `feat: add qlib control interaction panel`。**

### Task 5: 重建 workflow builder、示例和 schema 校验

**Files:**
- Modify: `src/ty_quant_node/workflow.py`。
- Replace: `examples/mvp_workflow.json`、`examples/ty_factors_workflow.json`。
- Modify: `tests/test_workflow_schema.py`、`tests/test_comfyui_workflow_payload.py`。

**Interfaces:**
- `build_mvp_workflow()` 和 `build_ty_factors_workflow()` 生成 schema v2 widgets_values_named 和新路径派生值。
- `validate_workflow()` 校验节点输入顺序、schema v2 字段和完整连线。

- [ ] **Step 1: 写失败测试**：断言示例只包含 schema v2 字段和 `artifact_root`，API prompt 中不出现旧键。
- [ ] **Step 2: 运行 workflow 测试，确认失败。**
- [ ] **Step 3: 更新 builder、校验器和 prompt 转换，删除旧示例后重新生成两个 JSON。**
- [ ] **Step 4: 运行 `uv run pytest ty-quant-node/tests/test_workflow_schema.py ty-quant-node/tests/test_comfyui_workflow_payload.py -q`。**
- [ ] **Step 5: 提交 `feat: rebuild schema v2 workflows`。**

### Task 6: 文档、全量验证和 ComfyUI 联调

**Files:**
- Modify: `README.md`、`CHANGELOG.md`。
- Modify: `tests/test_registration_contract.py`、必要时补充 `tests/test_node_contracts.py`。

- [ ] **Step 1: 更新 README 的 QlibControl 字段表、路径选择器、日期控件和旧工作流迁移说明。**
- [ ] **Step 2: 运行 `uv run pytest ty-quant-node/tests -q`，确认全量通过。**
- [ ] **Step 3: 运行 `uv lock --check`、`uv run python -m compileall -q ty-quant-node/src`、`git -C ty-quant-node diff --check`。**
- [ ] **Step 4: 重启独立 8190，检查 `/object_info/QlibControl` 的新字段与 tooltip、目录 API 两个端点。**
- [ ] **Step 5: 通过 8190 `/prompt` 执行新版本地 CSV 和 Tushare MVP，核对 report artifact。**
- [ ] **Step 6: 将新版工作流复制到 `E:\ComfyUI_windows_portable-G314\ComfyUI\user\default\workflows\ty-qlib\`。**
- [ ] **Step 7: 提交 `docs: document qlib control ux v2` 并推送 GitHub。**
