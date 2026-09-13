# 预测产物不可变与运行一致性实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `QlibPredict` 生成带运行键、文件校验和、输入引用的不可变预测产物，并保证 Qlib 不可用时也执行统一随机种子初始化，从而满足预测到回测链路的可复现和可审计要求。

**Architecture:** 预测节点根据训练模型 manifest、Dataset manifest、特征集引用和 segment 计算稳定运行键，将信号写入模型目录下按运行键分目录的 artifact。artifact 使用现有 `artifact_transaction` 原子发布，manifest 记录输入哈希、行数、列契约和文件 SHA-256；相同运行键只读复用，运行键变化自动生成新目录。`QlibRuntime` 将种子初始化移到 Qlib 导入分支之前，compat 与真实 Qlib 路径保持一致。

**Tech Stack:** Python 3.10+, pandas, NumPy, pytest, 现有 `Handle`/`artifact_transaction`/`sha256_file` 工具。

**Spec:** `docs/specs/2026-09-12-qlib-comfyui-mvp-design.md` 与仓库 README 中关于运行键、manifest、原子发布和轻量句柄的约定。

## Global Constraints

- 节点仓库只能位于 `D:\work_station\ty-comfyui-node\ty-quant-node`，不得依赖 `ty-quant` 运行时。
- 所有节点输入输出保持英文公共字段名、中文显示名和现有 ComfyUI 类型契约。
- token、凭证和随机状态不得写入 workflow、日志或 artifact。
- 旧的已发布模型和信号文件不能被覆盖；路径必须继续经过节点白名单校验。
- 测试必须使用固定 fixture，不访问真实网络或修改 ComfyUI 内置 Python 环境。

### Task 1: 固定预测 artifact 契约

**Files:**
- Modify: `src/ty_quant_node/nodes.py:QlibPredict.run`
- Modify: `src/ty_quant_node/nodes.py:_file_hash`（仅在需要时复用现有实现）
- Test: `tests/test_node_workflow.py`
- Test: `tests/test_node_contracts.py`

**Interfaces:**
- Consumes: `QLIB_TRAINED_MODEL`、`QLIB_DATASET`、可选 `QLIB_FEATURE_SET` 和 `segment`。
- Produces: `QLIB_SIGNAL_TABLE`，路径为 `<model_path>/signals/<run_key前24位>/signal.parquet`，metadata 至少包含 `run_key`、`rows`、`columns`、`model_path`、`dataset_path`、`feature_set_path`、`files.signal`。

- [ ] **Step 1: 写失败测试**

```python
def test_prediction_artifact_is_versioned_and_reused(tmp_path):
    export = QlibExport().run(str(csv_path), "qfq", str(tmp_path / "provider"))[0]
    dataset = QlibDataset().run(export, "2024-01-01", "2024-01-03", "2024-01-04", "2024-01-06")[0]
    model = QlibModel().run("linear", "{}")[0]
    trained = QlibTrain().run(dataset, model, str(tmp_path / "model"))[0]
    first = QlibPredict().run(trained, dataset, "test")[0]
    second = QlibPredict().run(trained, dataset, "test")[0]

    assert first["path"] == second["path"]
    assert Path(first["path"]).name == "signal.parquet"
    assert Path(first["path"]).parent.parent.name == "signals"
    manifest = json.loads((Path(first["path"]).parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_key"] == first["metadata"]["run_key"]
    assert manifest["files"]["signal"] == first["metadata"]["files"]["signal"]
```

- [ ] **Step 2: 运行测试确认失败**

运行：`uv run pytest ty-quant-node/tests/test_node_workflow.py::test_prediction_artifact_is_versioned_and_reused -q`

预期：失败，因为当前输出路径是 `signal_test.parquet` 且没有 prediction manifest。

- [ ] **Step 3: 实现最小改动**

在 `QlibPredict.run` 中先解析并校验模型、Dataset、特征句柄，构造：

```python
run_key = _stable_json_hash({
    "model_manifest": model_manifest,
    "dataset_manifest": dataset_handle.metadata.get("manifest", {}),
    "feature_set_path": feature_path or "",
    "segment": segment,
})
target = _versioned_run_target(Path(model_handle.path) / "signals", run_key)
```

用 `artifact_transaction(target)` 写 `signal.parquet` 和 `manifest.json`；manifest 记录 `schema_version`, `run_key`, `segment`, `rows`, `columns`, `model_path`, `dataset_path`, `feature_set_path` 和 `files.signal`。若目标已有相同运行键且两个文件存在，读取 manifest 并直接返回缓存句柄。返回句柄的 path 指向 `signal.parquet`，metadata 同时保留 manifest 字段，确保下游 `QlibBacktest` 仍可直接读取 parquet。

- [ ] **Step 4: 运行测试确认通过**

运行：`uv run pytest ty-quant-node/tests/test_node_workflow.py::test_prediction_artifact_is_versioned_and_reused ty-quant-node/tests/test_node_contracts.py -q`

预期：全部通过，且旧测试中对信号内容的断言保持有效。

- [ ] **Step 5: 提交**

```bash
git add src/ty_quant_node/nodes.py tests/test_node_workflow.py tests/test_node_contracts.py
git commit -m "feat: version prediction artifacts"
```

### Task 2: 统一 QlibRuntime 随机种子初始化

**Files:**
- Modify: `src/ty_quant_node/nodes.py:QlibRuntime.run`
- Test: `tests/test_registration_contract.py`

**Interfaces:**
- Consumes: 现有 `provider_uri`、`region`、`seed`、`experiment_uri`。
- Produces: 现有 `QLIB_RUNTIME` 句柄；真实 Qlib 与 compat 分支均在返回前设置 Python `random` 和 NumPy seed。

- [ ] **Step 1: 写失败测试**

新增 monkeypatch 测试，让 `qlib` 导入失败后检查 `random.seed` 和 `numpy.random.seed` 仍被调用一次。

- [ ] **Step 2: 运行测试确认失败**

运行：`uv run pytest ty-quant-node/tests/test_registration_contract.py -q`

预期：新增断言失败，因为当前 `ModuleNotFoundError` 分支提前返回。

- [ ] **Step 3: 实现最小改动**

将 `random.seed(int(seed))` 和 `np.random.seed(int(seed))` 放到 Qlib 导入尝试之前；保留真实 Qlib 初始化失败的错误分类和现有句柄 metadata。

- [ ] **Step 4: 运行测试确认通过**

运行：`uv run pytest ty-quant-node/tests/test_registration_contract.py -q`

预期：全部通过。

- [ ] **Step 5: 提交**

```bash
git add src/ty_quant_node/nodes.py tests/test_registration_contract.py
git commit -m "fix: seed compat qlib runtime"
```

### Task 3: 更新产品文档与全量验证

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_node_workflow.py`, `tests/test_registration_contract.py`, 全量测试套件

- [ ] **Step 1: 更新文档**

说明预测信号的实际 artifact 布局、manifest 字段和相同运行键复用规则；把变更加入“未发布”变更记录。

- [ ] **Step 2: 运行完整验证**

运行：

```powershell
uv run pytest ty-quant-node/tests -q
uv lock --check
uv run python -m compileall ty-quant-node/src
```

预期：测试零失败、锁文件检查通过、源码编译通过。

- [ ] **Step 3: 检查工作区与提交**

运行：`git diff --check; git status --short --branch`

确认无空白错误，提交只包含本计划涉及的文件。

## 自审清单

- Spec coverage：Task 1 覆盖预测 artifact 不可变和回测兼容；Task 2 覆盖 compat/真实 Qlib 随机性一致；Task 3 覆盖用户文档、变更记录和质量门禁。
- Placeholder scan：计划中的每一步都给出了文件、命令、接口或具体实现内容，没有 TBD/TODO。
- Type consistency：`QLIB_SIGNAL_TABLE` 句柄 path 始终是 `signal.parquet`，下游 `QlibBacktest` 继续按 path 读取；manifest 通过 metadata 传递运行键与文件 hash。
