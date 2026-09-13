# TY-Factors 数据节点与因子计算实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `ty-quant-node` 增加 PIT Tushare 数据链路、Qlib 转换和可版本化的 `TY-Factors` 计算节点，同时修正现有复权 factor 语义和节点参数契约。

**Architecture:** raw market data、corporate action snapshot、PIT adjusted fields 和 factor artifacts 分层保存。`TushareDailyFetch` 只负责采集，`TushareToQlib` 负责校验和一次性生成 Qlib/PIT 字段，`TYFactorCompute` 负责加载注册表、编译/计算表达式与缓存；Alpha158 作为独立 benchmark 读取相同的复权 provider。

**Tech Stack:** Python 3.12、pandas、numpy、pyarrow、Qlib、pytest、ComfyUI custom nodes。

**Spec:** `docs/specs/2026-09-13-ty-factors-data-nodes-design.md`

## Global Constraints

- 节点仓库只能位于 `D:\work_station\ty-comfyui-node\ty-quant-node`，不得依赖 `ty-quant` 运行时。
- Tushare token 只能来自环境变量或服务器配置，不进入 workflow、句柄 metadata、日志和 artifact。
- 原始数据不可覆盖；provider 和因子结果通过 `snapshot_id`/hash 版本化。
- 复权因子缺失、非正值、日期重复或合并不唯一时必须报错，不能静默填 1。
- 新增功能先写失败测试，再写最小实现；每个任务独立运行测试。

### Task 1: 统一复权因子语义

**Files:**
- Modify: `src/ty_quant_node/data/__init__.py`
- Modify: `src/ty_quant_node/backend/market.py`
- Modify: `src/ty_quant_node/core/handles.py`
- Test: `tests/test_adjustment.py`
- Test: `tests/test_core_contract.py`

**Interfaces:** `apply_adjustment()` 输出 `factor`（adjusted/original）和 raw 字段；`export_qlib()` 将标准 Qlib factor 写入 `factor.day.bin`，并把 `vwap` 与 manifest 语义写入 provider。

- [ ] **Step 1: 写失败测试**：断言 qfq 的 `factor=[0.5,1.0]`、none 的 factor 全为 1、provider 的 factor bin 与 adjusted close/raw close 比值一致，并要求 `$vwap` 文件存在。
- [ ] **Step 2: 运行 `uv run pytest ty-quant-node/tests/test_adjustment.py ty-quant-node/tests/test_core_contract.py -q`，确认因子语义测试失败。**
- [ ] **Step 3: 实现归一化 factor、PIT 字段别名、vwap 计算和 manifest 字段。**
- [ ] **Step 4: 重跑同一测试并确认通过。**
- [ ] **Step 5: 提交 `fix: align qlib factor semantics with adjusted prices`。**

### Task 2: PIT 事件与快照数据层

**Files:**
- Create: `src/ty_quant_node/data/pit_adjustment.py`
- Modify: `src/ty_quant_node/data/tushare_source.py`
- Test: `tests/test_pit_adjustment.py`
- Test: `tests/test_tushare_source.py`

**Interfaces:** `build_pit_adjustment(frame, events, snapshot_id) -> DataFrame`；`TushareDailySource.fetch()` 支持 raw daily、adj_factor 和可选事件表，并输出 `knowledge_time`/hash metadata。

- [ ] **Step 1: 写失败测试**：未来日期新增事件不改变过去的 PIT factor/close；事件日期排序、重复事件和缺失 multiplier 报错；fake transport 验证事件合并和 token 不泄漏。
- [ ] **Step 2: 运行 `uv run pytest ty-quant-node/tests/test_pit_adjustment.py ty-quant-node/tests/test_tushare_source.py -q`，确认失败。**
- [ ] **Step 3: 实现事件累积、snapshot metadata、daily/adj_factor/event 请求和严格合并。**
- [ ] **Step 4: 重跑测试并确认通过。**
- [ ] **Step 5: 提交 `feat: add point-in-time market adjustment snapshots`。**

### Task 3: 新增 Tushare 采集与 Qlib 转换节点

**Files:**
- Modify: `src/ty_quant_node/nodes.py`
- Modify: `src/ty_quant_node/backend/market.py`
- Test: `tests/test_node_contracts.py`
- Test: `tests/test_tushare_nodes.py`

**Interfaces:** `TushareDailyFetch.run(config, ts_codes, start_date, end_date, snapshot_dir) -> MARKET_DATA`；`TushareToQlib.run(market_data, adjustment_policy, output_dir, incremental) -> QLIB_EXPORT`。

- [ ] **Step 1: 写失败测试**：检查两个节点的 INPUT_TYPES、RETURN_TYPES、句柄 kind、路径产物、PIT/vendor_qfq 参数和坏输入错误。
- [ ] **Step 2: 运行节点测试并确认失败。**
- [ ] **Step 3: 实现节点，将采集和转换职责拆开，保留旧 `TushareDailyFetch` 的兼容别名。**
- [ ] **Step 4: 重跑节点测试及现有 workflow 测试。**
- [ ] **Step 5: 提交 `feat: add tushare snapshot and qlib conversion nodes`。**

### Task 4: TY-Factors 注册表与计算后端

**Files:**
- Create: `src/ty_quant_node/factors/registry.py`
- Create: `src/ty_quant_node/factors/compute.py`
- Create: `src/ty_quant_node/factors/builtin/ty_momentum.yaml`
- Create: `src/ty_quant_node/factors/builtin/ty_volatility.yaml`
- Create: `src/ty_quant_node/factors/builtin/ty_volume.yaml`
- Modify: `src/ty_quant_node/core/handles.py`
- Test: `tests/test_factor_registry.py`
- Test: `tests/test_factor_compute.py`

**Interfaces:** `load_factor_specs(root) -> list[FactorSpec]`；`compute_ty_factors(provider_path, factor_set, selected, custom, output_dir) -> Handle`。表达式只允许白名单字段、函数和受控 Qlib operators；输出 manifest 记录 formula/version/lookback/provider snapshot。

- [ ] **Step 1: 写失败测试**：YAML schema 校验、重复名称拒绝、`TY_MOM_20` 正确使用 `ty_close`、缺少预热窗口时输出 NaN/质量错误、缓存命中不重复写文件。
- [ ] **Step 2: 运行因子测试并确认失败。**
- [ ] **Step 3: 实现注册表、白名单表达式解析、PIT 字段计算、Alpha158 配置加载和 artifact cache。**
- [ ] **Step 4: 重跑测试并确认通过。**
- [ ] **Step 5: 提交 `feat: add versioned ty-factors registry and compute backend`。**

### Task 5: 打磨现有节点契约与工作流

**Files:**
- Modify: `src/ty_quant_node/nodes.py`
- Modify: `src/ty_quant_node/workflow.py`
- Modify: `examples/mvp_workflow.json`
- Create: `examples/ty_factors_workflow.json`
- Test: `tests/test_registration_contract.py`
- Test: `tests/test_workflow_schema.py`

**Interfaces:** 所有阶段节点的 required/optional 输入顺序、默认值、控制节点覆盖规则和输出类型与文档一致；新工作流覆盖 raw→PIT→Qlib→TY-Factors→训练/回测。

- [ ] **Step 1: 写失败测试**：控制节点不能覆盖数据句柄路径；节点默认参数可在 ComfyUI 0.4 workflow 恢复；新 workflow 所有 link 双向一致。
- [ ] **Step 2: 运行 schema/registration 测试并确认失败。**
- [ ] **Step 3: 调整端口名称、参数范围、错误信息和 workflow builder。**
- [ ] **Step 4: 重跑全部 `uv run pytest ty-quant-node/tests -q`。**
- [ ] **Step 5: 提交 `refactor: polish qlib node contracts and ty-factors workflow`。**

### Task 6: 独立联调、文档和 ComfyUI 验证

**Files:**
- Modify: `README.md`
- Modify: `docs/specs/2026-09-13-ty-factors-data-nodes-design.md`
- Modify: `examples/ty_factors_workflow.json`

- [ ] **Step 1: 使用 fixture 运行 raw→PIT→Qlib→TY-Factors→训练→回测完整链路。**
- [ ] **Step 2: 使用 fake Tushare server 运行节点级流程，确认 token、snapshot 和缓存不泄漏敏感信息。**
- [ ] **Step 3: 运行 `uv lock --check` 和全部测试，记录结果。**
- [ ] **Step 4: 复制工作流到 `E:\ComfyUI_windows_portable-G314\ComfyUI\user\default\workflows\ty-qlib`，重启 ComfyUI，确认 `/object_info` 注册节点和 `/prompt` 执行产物。**
- [ ] **Step 5: 提交 `docs: document ty-factors data and workflow usage` 并同步 GitHub。**
