# 总控节点统一扇出实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**目标：** 让 `QlibControl` 成为本地 CSV 与 Tushare→PIT→TY-Factors 两条工作流共同使用的配置总控，并让 ComfyUI 工作流中的日期、复权、因子、模型和回测参数只有一个权威来源。

**架构：** `QlibControl` 保留现有本地 CSV 与训练/回测字段，增加 Tushare、PIT 和因子字段并写入 `QLIB_CONTROL.metadata`。数据、转换和因子节点增加可选 `control` 输入，只读取与自身契约匹配的键；凭证仍由 `TushareConfig` 单独负责。工作流 builder 生成一个总控节点扇出到所有阶段节点，旧的直接参数调用继续兼容。

**技术栈：** Python 3.12、pandas、pytest、ComfyUI 0.4 workflow JSON。

**规格：** `docs/specs/2026-09-13-ty-factors-data-nodes-design.md`。

## 全局约束

- 节点仓库只能位于 `D:\work_station\ty-comfyui-node\ty-quant-node`，不依赖 `ty-quant` 运行时。
- token 只从环境变量读取，不进入控制句柄、workflow、日志或 artifact。
- 旧节点调用签名和本地 CSV MVP 行为保持兼容。
- 所有路径仍经节点白名单校验，工作流不嵌入行情表或模型内容。
- 每个行为先写失败测试，再写最小实现；测试必须使用固定 fixture 或 fake source。

### Task 1：控制句柄字段与节点覆盖契约

**文件：** `src/ty_quant_node/nodes.py`、`tests/test_control_node.py`、`tests/test_tushare_nodes.py`、`tests/test_node_contracts.py`。

- [x] 写失败测试：控制句柄保存 `ts_codes/start_date/end_date/snapshot_dir/include_events/adjustment_policy/incremental/factor_set/selected_json/custom_json/factor_output_dir`；`TushareDailyFetch`、`TushareToQlib`、`TYFactorCompute` 在传入冲突的直接参数时采用控制句柄值。
- [x] 运行定向测试并确认失败原因是节点没有 `control` 输入或没有读取新字段。
- [x] 为 `QlibControl.INPUT_TYPES` 增加可选 Tushare/PIT/TY-Factors widgets；`run` 将非凭证配置写入 metadata，不保存 token。
- [x] 为三个数据/因子节点增加可选 `QLIB_CONTROL` 输入，并按字段覆盖自身参数；不改变 `TushareConfig` 的安全边界。
- [x] 重跑定向测试和现有控制节点测试。

### Task 2：Tushare 工作流改为总控拓扑

**文件：** `src/ty_quant_node/workflow.py`、`examples/mvp_workflow.json`、`examples/ty_factors_workflow.json`、`tests/test_workflow_schema.py`、`tests/test_comfyui_workflow_payload.py`。

- [x] 写失败测试：`build_ty_factors_workflow` 包含一个 `QlibControl`，其输出同时连接 Tushare、PIT、因子、Dataset、模型、训练、预测、回测和报告节点；所有链接在来源和目标槽位双向一致。
- [x] 运行 workflow schema 测试并确认当前 Tushare 工作流缺少总控节点。
- [x] 调整 builder 的稳定节点 ID、链接、分组和 widget 值；本地 MVP builder 同步写入新增可选 control widgets。
- [x] 生成两个 0.4 workflow JSON，执行 `validate_workflow` 与 `workflow_to_prompt` 检查。
- [x] 重跑全部 workflow/registration 测试。

### Task 3：文档、独立联调和发布

**文件：** `README.md`、`docs/specs/2026-09-13-ty-factors-data-nodes-design.md`。

- [x] 补充总控字段、覆盖优先级和 Tushare token 仍由 `TushareConfig` 管理的说明。
- [x] 使用 fake Tushare source 执行节点链路，确认控制参数生效且 token 不泄漏。
- [x] 重启独立 ComfyUI 8190，提交本地 MVP 工作流并确认 API `success`、artifact manifest 和报告图片；Tushare 工作流已通过 schema、fake source 完整链路和总控覆盖验证。
- [ ] 使用用户配置的真实 Tushare token 在 ComfyUI 8190 提交 Tushare 工作流，确认权限、限流和真实数据质量报告。
- [x] 运行 `uv run pytest ty-quant-node/tests -q`、`uv lock --check`、`git diff --check`，提交并推送。
