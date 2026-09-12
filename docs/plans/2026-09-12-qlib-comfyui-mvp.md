# Qlib ComfyUI MVP 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在独立 `ty-quant-node` 仓库中，把行情复权、Qlib 导出、DatasetH、模型训练、预测、TopK 回测和报告组成可运行的 ComfyUI MVP。

**架构：** `src/ty_quant_node` 分为数据、后端、核心和节点适配层。节点只传递带版本和路径的轻量句柄；DataFrame、模型文本和净值曲线写入本地 artifact。共享 Python 3.12 环境执行真实 Qlib，便携版 ComfyUI Python 3.14 缺少兼容 Qlib 时使用相同 `prepare(segment)` 契约的兼容数据集。

**技术栈：** Python 3.12、Qlib 0.9.7、pandas、numpy、pyarrow、LightGBM、matplotlib、pytest、ComfyUI node API。

**规格：** `docs/specs/2026-09-12-qlib-comfyui-mvp-design.md`

## 全局约束

- 仓库路径固定为 `D:\work_station\ty-comfyui-node\ty-quant-node`，独立 Git 历史和 GitHub 仓库。
- 文档和错误信息使用中文；公共代码 API 使用清晰英文命名。
- 原始 OHLCV 和 `adj_factor` 双轨保存；默认 `qfq`，金额不复权，成交量反向调整。
- 默认 seed 为 42；workflow JSON 只保存句柄元数据，不保存大表或模型二进制。
- 离线测试使用固定 fixture；命令为 `uv run pytest ty-quant-node/tests -q`。
- Tushare token 只从环境变量读取，不进入 workflow、日志和缓存键。

## 已落地任务

### 任务 1：仓库和注册入口

文件：根目录 `__init__.py`、`pyproject.toml`、`README.md`、`LICENSE`、`src/ty_quant_node/__init__.py`。

- [x] 建立独立包和 ComfyUI 加载入口。
- [x] 注册 11 个节点：`QlibRuntime`、`TushareConfig`、`TushareDailyFetch`、`AdjustPrices`、`QlibExport`、`QlibDataset`、`QlibModel`、`QlibTrain`、`QlibPredict`、`QlibBacktest`、`QlibReport`。
- [x] 配置 setuptools 构建和 Python 3.12 依赖。

### 任务 2：句柄、路径和缓存

文件：`src/ty_quant_node/core/handles.py`、`core/security.py`、`core/cache.py`。

- [x] `Handle.to_dict/from_dict` 校验已知类型、版本和元数据。
- [x] `resolve_allowed_path` 拒绝 URL、设备路径、路径穿越和白名单外路径。
- [x] `cache_key` 使用规范化配置、输入 hash 和版本生成 SHA-256 键。

### 任务 3：行情、复权、Tushare 和 Qlib 导出

文件：`src/ty_quant_node/data/__init__.py`、`data/tushare_source.py`、`backend/market.py`。

- [x] 规范化本地字段和 Tushare `daily` 字段。
- [x] 分别调用 `daily` 与 `adj_factor`，合并 raw+factor，并区分网络、权限和无数据错误。
- [x] 实现 `none/qfq/hfq`、anchor 日期/因子、缺失因子阻止策略。
- [x] 写出 `calendars/day.txt`、`instruments/all.txt`、`features/*/*.day.bin`、`dataset.parquet` 和 `manifest.json`。
- [x] 校验 calendar、bin 长度和 instruments/features 集合一致；真实 Qlib `D.features` 可读取导出 provider。

### 任务 4：DatasetH、模型和预测

文件：`src/ty_quant_node/backend/qlib_backend.py`、`backend/model_backend.py`。

- [x] 从 adjusted frame 构造 `feature_return` 和下一日 `label`。
- [x] 使用 Qlib `DatasetH + DataHandlerLP + StaticDataLoader`；ComfyUI 3.14 无 Qlib 时回退兼容实现。
- [x] 支持 Linear 和 LightGBM，模型保存为 JSON 或 LightGBM 文本，不加载未知 pickle。
- [x] 输出包含 `instrument`、`datetime`、`score` 的 signal 表。

### 任务 5：回测和报告

文件：`src/ty_quant_node/backend/backtest_backend.py`、`core/report.py`。

- [x] 实现 TopK、Dropout、交易成本、空信号和单日边界。
- [x] 输出累计收益、年化收益、最大回撤、Sharpe、IC、RankIC、交易次数和净值曲线。
- [x] 生成 RGB PNG、JSON 摘要和 ComfyUI `IMAGE` 张量。

### 任务 6：节点级串联

文件：`src/ty_quant_node/nodes.py`、`examples/mvp_workflow.json`。

- [x] 实现数据、Qlib、模型、回测和报告节点的 INPUT/OUTPUT 契约。
- [x] 固定 fixture 节点测试覆盖导出 -> DatasetH -> 训练 -> 预测 -> 回测 -> 报告。
- [x] 报告节点标记 `OUTPUT_NODE=True`，可被 ComfyUI `/prompt` 执行。

### 任务 7：验证、联调和发布

文件：`tests/`、`tests/fixtures/market.csv`、`README.md`。

- [x] `uv lock --check`、`uv sync --locked`、`uv run pytest ty-quant-node/tests -q` 通过。
- [x] 建立 `E:\ComfyUI_windows_portable-G314\ComfyUI\custom_nodes\ty-quant-node` junction。
- [x] 重启真实 ComfyUI，`/object_info` 发现全部节点，API fixture workflow 返回 `execution_success` 并生成报告文件。
- [x] 创建并推送公开 GitHub 仓库 `https://github.com/yuanyuli/ty-quant-node` 的 `master` 分支。

## 验收命令

```powershell
cd D:\work_station\ty-comfyui-node
uv lock --check
uv sync --locked
uv run pytest ty-quant-node/tests -q
```

验收通过标准是所有测试通过，且 ComfyUI API workflow 返回 `status_str=success`、`completed=true`，artifact 目录包含 provider manifest、模型文件、回测 metrics 和 RGB equity PNG。
