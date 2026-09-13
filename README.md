# ty-quant-node

`ty-quant-node` 是一个独立维护的 Qlib ComfyUI 节点组。它把日频行情、复权、Qlib 数据导出、DatasetH、模型训练、预测、TopK 回测和报告串成一条可复现的工作流。实现参考 Qlib 的 DatasetH、模型和回测边界，也参考 `ty-quant` 的数据源和数据版本思路，但运行时不依赖 `ty-quant`、FastAPI、Redis 或数据库。

## MVP 流程

```text
TushareConfig / 本地 CSV
    -> TushareDailyFetch 或 QlibExport
    -> QlibDataset (DatasetH)
    -> QlibModel -> QlibTrain -> QlibPredict
    -> QlibBacktest -> QlibReport
```

当前节点：`QlibControl`、`QlibRuntime`、`TushareConfig`、`TushareDailyFetch`、`AdjustPrices`、`QlibExport`、`QlibDataset`、`QlibModel`、`QlibTrain`、`QlibPredict`、`QlibBacktest`、`QlibReport`。

`QlibControl` 是 H3 导演工作台风格的总控节点。它集中保存 CSV 路径、复权方式、训练/测试区间、模型参数、回测参数和报告目录，再通过 `QLIB_CONTROL` 句柄扇出到各阶段节点。各阶段仍然独立执行，便于替换数据源或定位问题。

节点之间传递的是带 `kind/version/path/metadata` 的轻量句柄，行情表、模型文件和净值曲线写入本地 artifact 目录，不塞进 workflow JSON。

## 数据与复权口径

输入可以是 CSV 或 Parquet。原始字段至少包括：`instrument`、`datetime`、`open_raw`、`high_raw`、`low_raw`、`close_raw`、`volume_raw`、`adj_factor`。Tushare 字段 `ts_code/trade_date/open/high/low/close/vol/amount` 会自动规范化。

原始 OHLCV 永远保留，派生字段按选择的口径生成：

```text
qfq: adjusted_price = raw_price * adj_factor / anchor_factor
hfq: adjusted_price = raw_price * adj_factor
volume: volume_raw * anchor_factor / adj_factor
amount: 保持原始口径
```

MVP 的 anchor 是查询区间最后一个有效复权因子，并写入 `manifest.json`。复权因子缺失或非正时默认阻止训练和回测；只有显式传入 `allow_unadjusted=True` 的库层调用才会用 1 降级。

## 环境与测试

仓库使用总目录的共享环境 `D:\work_station\ty-comfyui-node\.venv`。先在总目录同步依赖：

```powershell
cd D:\work_station\ty-comfyui-node
uv sync
uv run pytest ty-quant-node/tests -q
```

独立 fixture 测试不访问网络，包含复权因子变化、Qlib 二进制 provider 读取、DatasetH、Linear/LightGBM、回测指标、报告 PNG 和节点级 workflow。

共享 `.venv` 中会使用真实 Qlib `DatasetH`。当前便携版 ComfyUI 是 Python 3.14，而 Qlib 依赖的共享 NumPy 是 Python 3.12 构建；在该解释器中节点会自动使用等价的本地 `prepare(segment)` 兼容层，不需要修改 ComfyUI 内置环境。将来 ComfyUI 环境具备兼容版本的 Qlib 时会自动切换到真实实现。

## Tushare

只在运行 ComfyUI 的进程环境配置 token，不把 token 写入 workflow、日志或 artifact：

```powershell
$env:TUSHARE_TOKEN = "你的 token"
```

`TushareDailyFetch` 分别调用 `daily` 和 `adj_factor`，再按 `ts_code + trade_date` 合并。网络错误会重试，认证、权限错误和无数据会给出不同的中文错误。

## 接入本地 ComfyUI

本地 ComfyUI 目录为 `E:\ComfyUI_windows_portable-G314\ComfyUI`。独立测试通过后建立 junction，不复制源码：

```powershell
cmd /c mklink /J "E:\ComfyUI_windows_portable-G314\ComfyUI\custom_nodes\ty-quant-node" "D:\work_station\ty-comfyui-node\ty-quant-node"
```

重启 ComfyUI 后端，搜索 `TY Quant` 节点；修改 Python 后重新启动后端，修改前端资源后刷新浏览器。示例 workflow 位于 `examples/mvp_workflow.json`，固定输入位于 `tests/fixtures/market.csv`。工作流使用完整 ComfyUI 0.4 编辑器格式，包含 `TY Quant 控制台`、数据准备、模型训练和回测报告四个分组；本地安装副本位于 `E:\ComfyUI_windows_portable-G314\ComfyUI\user\default\workflows\ty-qlib\mvp_workflow.json`。

工作流结构由 `src/ty_quant_node/workflow.py` 生成和校验。独立验证使用 `uv run pytest ty-quant-node/tests -q`；真实 ComfyUI 联调将生成 `.artifacts/comfyui-mvp/provider`、`.artifacts/comfyui-mvp/model` 和 `.artifacts/comfyui-mvp/report/equity.png`。

## 代码结构

```text
src/ty_quant_node/
  core/       句柄、路径安全、缓存、报告
  data/       复权和 Tushare 适配器
  backend/    Qlib 导出、DatasetH、模型、回测
  nodes.py    ComfyUI 注册和输入输出转换
tests/        固定 fixture 与端到端验收
docs/         设计规格和实施计划
research/     调研归档，不是运行时依赖
```

## 当前边界

首版面向本地 Windows ComfyUI 和日频研究。它不提交券商订单、不提供远程多用户服务，也不加载未知 pickle。滚动训练、Alpha158、风险模型和更丰富的前端展示作为后续独立版本。
