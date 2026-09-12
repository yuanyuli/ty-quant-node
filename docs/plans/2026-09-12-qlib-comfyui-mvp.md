# Qlib ComfyUI MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在独立 `qlib-comfyui` 仓库中实现 Qlib 离线研究、训练、预测、回测和报告的 ComfyUI MVP。

**Architecture:** 以版本化 dataclass 句柄连接节点，QlibBackend 封装 Qlib API；任务结果写入白名单缓存目录，节点只传递轻量元数据。ComfyUI 层负责 INPUT_TYPES、注册和输出转换，领域层保持可离线测试。

**Tech Stack:** Python 3.10+、Qlib、pandas、numpy、LightGBM、matplotlib、pytest、ComfyUI node API。

**Spec:** `docs/superpowers/specs/2026-09-12-qlib-comfyui-mvp-design.md`

## Global Constraints

- 仓库必须位于 `D:\work_station\ty-comfyui-node\qlib-comfyui` 并独立维护。
- 所有文档、README、错误信息使用中文；公共代码 API 使用清晰英文命名。
- 不依赖 `civitai-inspiration` 或父项目运行时代码；共享仅限父目录 uv 环境。
- 只允许白名单路径；禁止 URL、路径穿越和任意 pickle 加载。
- 默认随机种子为 42；缓存键包含输入 hash、Qlib 版本和节点版本。
- 测试必须使用固定 fixture，命令为 `uv run pytest qlib-comfyui/tests -q`。

### Task 1: 初始化独立仓库与测试骨架

**Files:** Create `qlib-comfyui/__init__.py`, `qlib-comfyui/pyproject.toml`, `qlib-comfyui/README.md`, `qlib-comfyui/LICENSE`, `qlib-comfyui/tests/conftest.py`, `qlib-comfyui/tests/test_registration.py`.

- [ ] 写测试断言 `NODE_CLASS_MAPPINGS` 存在且包含七个节点名。
- [ ] 运行 `uv run pytest qlib-comfyui/tests/test_registration.py -q`，确认因模块不存在而失败。
- [ ] 创建最小包、pytest 配置和中文安装说明；先用占位节点映射满足导入。
- [ ] 重跑测试并提交 `chore: scaffold qlib comfyui package`。

### Task 2: 句柄、路径安全与缓存

**Files:** Create `qlib-comfyui/core/handles.py`, `core/security.py`, `core/cache.py`, `tests/test_core.py`.

- [ ] 测试 `Handle(kind, version, path, metadata).to_dict()/from_dict()` 往返、拒绝未知 kind、拒绝白名单外路径和 `..`。
- [ ] 实现 `Handle`、`resolve_allowed_path(path, roots)`、`Cache.key(config, input_hashes, versions)` 和存在性校验。
- [ ] 运行核心测试并提交 `feat: add safe versioned handles and cache`。

### Task 3: QlibBackend 与数据集构建

**Files:** Create `qlib_comfyui/backend/protocol.py`, `backend/qlib_backend.py`, `core/config.py`, `tests/fixtures/market.csv`, `tests/test_backend_dataset.py`.

- [ ] 用 fixture 测试 CSV schema（instrument、datetime、feature、label）、日期 segment 和缺失字段错误。
- [ ] 定义 `QuantBackend.build_dataset(config) -> Handle`；实现 provider 初始化、CSV/Parquet 读取、DatasetH/DataHandler 构造和 schema 元数据。
- [ ] 在测试环境用临时 provider/cache 目录，验证 dataset 句柄可序列化；提交 `feat: build offline qlib datasets`。

### Task 4: 模型规格、训练与预测

**Files:** Create `backend/model_backend.py`, `nodes/model_nodes.py`, `tests/test_train_predict.py`; Modify `__init__.py`.

- [ ] 测试 `lightgbm` 与 `linear` 两种 model spec，训练后预测表包含 instrument、datetime、score，且结果行数与 test segment 一致。
- [ ] 实现 `QlibModel` 参数 JSON 校验、`QlibTrain` fit/recorder 摘要、`QlibPredict` segment 选择；将模型文件放入缓存目录并记录输入 hash。
- [ ] 运行训练预测测试并提交 `feat: add qlib training and prediction nodes`。

### Task 5: 回测与指标

**Files:** Create `backend/backtest_backend.py`, `nodes/backtest_nodes.py`, `tests/test_backtest.py`.

- [ ] 测试 TopK/Dropout 组合、交易成本、空信号、单日数据和缺失值；断言累计收益、年化、最大回撤、交易次数字段存在。
- [ ] 实现 `QuantBackend.backtest(signal, config)`，输出版本化结果句柄、CSV 净值和指标 JSON；数值不足的 Sharpe/IC 返回 null。
- [ ] 运行回测测试并提交 `feat: add qlib backtest node`。

### Task 6: 报告输出与 ComfyUI 注册

**Files:** Create `nodes/runtime_node.py`, `nodes/dataset_node.py`, `nodes/report_node.py`, `core/report.py`, `tests/test_report.py`; Modify `__init__.py`.

- [ ] 测试报告生成 RGB PNG、摘要 JSON 和 ComfyUI `IMAGE` 张量形状；测试七个节点的 INPUT_TYPES 与类别名。
- [ ] 实现 Runtime、Dataset、Model、Train、Predict、Backtest、Report 节点及 `NODE_DISPLAY_NAME_MAPPINGS`；报告加载 PNG 为 tensor 并返回中文摘要。
- [ ] 运行全部单测并提交 `feat: register qlib mvp nodes and reports`。

### Task 7: 文档、示例与真实环境验证

**Files:** Create `qlib-comfyui/examples/mvp_workflow.json`, `qlib-comfyui/tests/test_e2e_fixture.py`; Modify `README.md`.

- [ ] 编写离线端到端测试，从 fixture 运行七节点闭环并断言报告文件存在。
- [ ] 加入 junction 命令、Qlib 数据目录配置、缓存清理、ComfyUI 重启说明和示例 workflow。
- [ ] 运行 `uv run pytest qlib-comfyui/tests -q`；在 ComfyUI 建立 junction 后重启后端，确认节点可搜索并执行示例。
- [ ] 提交 `docs: document qlib comfyui mvp usage`。
