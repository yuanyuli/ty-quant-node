# Artifact 完整性链实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让模型、预测信号、回测结果和报告在消费前校验 manifest 文件哈希，阻止被篡改或不完整的中间产物继续进入量化结果。

**Architecture:** 在 `core.artifacts` 增加只读 `verify_manifest_file` 辅助函数，统一检查相对文件存在、manifest 中有预期 SHA-256 且实际哈希一致。模型加载、`QlibBacktest` 和 `QlibReport` 在读取各自输入前调用它；legacy artifact 没有 manifest 时保留已有兼容行为，但新节点生成的 artifact 必须经过完整校验。

**Tech Stack:** Python 3.10+, pathlib, hashlib, pandas, pytest。

**Spec:** `docs/specs/2026-09-12-qlib-comfyui-mvp-design.md` 中的 manifest、原子发布、轻量句柄和可复核产物约定。

## Global Constraints

- 所有改动只发生在 `D:\work_station\ty-comfyui-node\ty-quant-node`，不得依赖 `ty-quant` 运行时。
- 校验失败必须抛出 `ValueError` 子类并包含中文的“hash”或“完整性”信息。
- 不自动修复、覆盖或删除损坏 artifact；旧版本目录保持只读语义。
- 现有 ComfyUI 输入输出类型和 legacy 无 manifest 的读取兼容性保持不变。
- 测试使用固定 fixture，不访问真实 Tushare 网络或修改 ComfyUI 内置 Python。

### Task 1: 增加通用 manifest 文件校验

**Files:**
- Modify: `src/ty_quant_node/core/artifacts.py`
- Test: `tests/test_artifacts.py`

**Interfaces:**
- Produces: `ArtifactIntegrityError(ValueError)` 和 `verify_manifest_file(root, manifest, key, relative_path=None) -> Path`。

- [ ] **Step 1: 写失败测试**

```python
def test_verify_manifest_file_rejects_tampered_content(tmp_path):
    target = tmp_path / "signal.parquet"
    target.write_bytes(b"original")
    manifest = {"files": {"signal": "0" * 64}}

    with pytest.raises(ValueError, match="hash"):
        verify_manifest_file(tmp_path, manifest, "signal")
```

- [ ] **Step 2: 运行测试确认失败**

运行：`uv run pytest ty-quant-node/tests/test_artifacts.py::test_verify_manifest_file_rejects_tampered_content -q`

预期：失败，因为校验函数尚不存在。

- [ ] **Step 3: 实现最小函数**

从 `manifest["files"][key]` 读取 64 位十六进制 hash，默认相对文件名为 `key`；拒绝绝对路径和包含 `..` 的 `relative_path`；文件不存在、hash 缺失、格式错误或 SHA-256 不一致都抛出 `ArtifactIntegrityError`。返回解析后的文件路径，不修改任何内容。

- [ ] **Step 4: 运行测试确认通过**

运行：`uv run pytest ty-quant-node/tests/test_artifacts.py -q`

预期：全部通过。

- [ ] **Step 5: 提交**

```bash
git add src/ty_quant_node/core/artifacts.py tests/test_artifacts.py
git commit -m "feat: add manifest integrity verifier"
```

### Task 2: 校验模型和回测输入

**Files:**
- Modify: `src/ty_quant_node/backend/model_backend.py:load_model`
- Modify: `src/ty_quant_node/nodes.py:QlibBacktest.run`
- Test: `tests/test_dataset_model_report.py`
- Test: `tests/test_node_workflow.py`

**Interfaces:**
- `load_model(handle)` 在存在模型 manifest 时校验 `files.model`，再读取 `model.json` 或 `model.txt`。
- `QlibBacktest.run` 在读取 signal parquet 前校验同目录 prediction manifest 的 `files.signal`，并继续返回 `QLIB_BACKTEST_RESULT`。

- [ ] **Step 1: 写失败测试**

生成完整节点链路后，修改训练模型的 `model.json` 或预测目录的 `signal.parquet`，分别断言 `QlibPredict`/`QlibBacktest` 抛出包含“hash”的 `ValueError`。

- [ ] **Step 2: 运行测试确认失败**

运行：`uv run pytest ty-quant-node/tests/test_node_workflow.py::test_consumers_reject_tampered_prediction_artifact -q`

预期：失败，因为当前消费者直接读取文件。

- [ ] **Step 3: 实现最小校验**

模型加载时读取 `manifest.json`（存在才校验），把模型文件名映射为 `model.json`/`model.txt`；回测读取 signal 同级 manifest，调用 `verify_manifest_file(signal_path.parent, manifest, "signal")`。兼容没有 manifest 的旧 signal 路径。

- [ ] **Step 4: 运行聚焦测试**

运行：`uv run pytest ty-quant-node/tests/test_dataset_model_report.py ty-quant-node/tests/test_node_workflow.py -q`

预期：完整链路和篡改拒绝测试全部通过。

- [ ] **Step 5: 提交**

```bash
git add src/ty_quant_node/backend/model_backend.py src/ty_quant_node/nodes.py tests/test_dataset_model_report.py tests/test_node_workflow.py
git commit -m "feat: verify model and signal artifacts"
```

### Task 3: 校验报告输入并更新文档

**Files:**
- Modify: `src/ty_quant_node/nodes.py:QlibReport.run`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_node_workflow.py`

- [ ] **Step 1: 写失败测试**

在生成回测结果后修改 `metrics.json`，调用 `QlibReport`，断言抛出完整性错误。

- [ ] **Step 2: 运行测试确认失败**

运行：`uv run pytest ty-quant-node/tests/test_node_workflow.py::test_report_rejects_tampered_backtest_artifact -q`

预期：失败，因为报告当前未验证回测 manifest。

- [ ] **Step 3: 实现和文档**

`QlibReport.run` 读取回测目录 manifest，分别校验 `metrics.json` 和 `equity.csv`；无 manifest 时保留 legacy 读取。README 增加“消费前完整性校验”说明，CHANGELOG 记录本阶段变更。

- [ ] **Step 4: 运行完整质量门禁**

```powershell
uv run pytest ty-quant-node/tests -q
uv lock --check
uv run python -m compileall ty-quant-node/src
git diff --check
git status --short --branch
```

预期：测试零失败，锁文件和编译检查通过，工作区只含本计划的提交。

- [ ] **Step 5: 提交并推送**

```bash
git add src/ty_quant_node/nodes.py README.md CHANGELOG.md tests/test_node_workflow.py docs/superpowers/plans/2026-09-13-artifact-integrity-chain.md
git commit -m "feat: enforce artifact integrity chain"
git push origin master
```

## 自审清单

- Spec coverage：Task 1 提供统一校验 API；Task 2 保护模型和信号；Task 3 保护回测报告并记录用户文档与质量门禁。
- Placeholder scan：每个步骤均有具体文件、接口、测试命令和预期结果，没有 TBD/TODO。
- Type consistency：`verify_manifest_file` 返回 `Path`；模型、回测、报告只把它用于只读校验，不改变现有句柄类型。
