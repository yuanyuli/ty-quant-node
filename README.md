# ty-quant-node

`ty-quant-node` 是一个独立维护的 Qlib ComfyUI 节点组。它把日频行情、复权、Qlib 数据导出、DatasetH、模型训练、预测、TopK 回测和报告串成一条可复现的工作流。实现参考 Qlib 的 DatasetH、模型和回测边界，也参考 `ty-quant` 的数据源和数据版本思路，但运行时不依赖 `ty-quant`、FastAPI、Redis 或数据库。

## 安装

基础安装包含数据处理、复权、TY-Factors 兼容计算和报告能力；需要真实 Qlib 的 DatasetH、Alpha158 或 LightGBM 时安装完整 extras：

```powershell
cd E:\ComfyUI_windows_portable-G314\ComfyUI\custom_nodes
git clone https://github.com/yuanyuli/ty-quant-node.git ty-quant-node
cd ty-quant-node
python -m pip install -e ".[full]"
```

仓库根部的 `__init__.py` 是 ComfyUI 扫描入口，不能只把 wheel 安装到 site-packages。Python 3.14 的 ComfyUI 便携版可先安装基础 extras，节点会使用兼容 Dataset；Alpha158 和真实 Qlib provider 计算需要 Python 3.10-3.13 环境并安装 `ty-quant-node[qlib]`。工作区开发仍统一使用总目录的 uv 环境。

## MVP 流程

```text
TushareConfig -> TushareDailyFetch -> TushareToQlib -> TYFactorCompute
    -> QlibDataset (DatasetH)
    -> QlibModel -> QlibTrain -> QlibPredict
    -> QlibBacktest -> QlibReport

本地 CSV 可以从 `QlibExport` 直接进入 Dataset；Tushare 链路会先保留 raw 快照，再生成 Qlib provider。
```

当前节点：`QlibControl`、`QlibRuntime`、`TushareConfig`、`TushareDailyFetch`、`TushareToQlib`、`TYFactorCompute`、`AdjustPrices`、`QlibExport`、`QlibDataset`、`QlibModel`、`QlibTrain`、`QlibPredict`、`QlibBacktest`、`QlibReport`。

`QlibControl` 是 H3 导演工作台风格的总控节点。它集中保存本地 CSV 或 Tushare 查询、复权方式、训练/测试区间、TY-Factors 选择、模型参数、回测参数和报告目录，再通过 `QLIB_CONTROL` 句柄扇出到各阶段节点。数据、转换、因子、Dataset、模型、训练、预测、回测和报告节点连接总控后，以总控字段为准；未连接总控时仍使用自身 widgets，便于替换数据源或定位问题。

节点之间传递的是带 `kind/version/path/metadata` 的轻量句柄，行情表、模型文件和净值曲线写入本地 artifact 目录，不塞进 workflow JSON。

所有可复用产物都遵循“运行键 + manifest + 原子发布”约定：相同输入快照、因子/模型参数和回测参数会命中同一个版本目录；参数或输入发生变化时写入新的短 hash 子目录，旧目录不覆盖。目录先在同级隐藏 staging 目录构建，只有 `raw.parquet`/`features.parquet`/模型文件/曲线和 manifest 全部成功后才提交；中途异常会自动清理 staging。训练、预测、回测和报告也各自保留 manifest，便于定位输入版本和重复复核。

## 数据与复权口径

输入可以是 CSV 或 Parquet。原始字段至少包括：`instrument`、`datetime`、`open_raw`、`high_raw`、`low_raw`、`close_raw`、`volume_raw`、`adj_factor`。Tushare 字段 `ts_code/trade_date/open/high/low/close/vol/amount` 会自动规范化。

原始 OHLCV 永远保留，派生字段按选择的口径生成：

```text
qfq: adjusted_price = raw_price * adj_factor / anchor_factor
hfq: adjusted_price = raw_price * adj_factor
volume: volume_raw * anchor_factor / adj_factor
amount: 保持原始口径
```

MVP 的 anchor 是查询区间最后一个有效复权因子，并写入 `manifest.json`。Tushare 链路默认使用 `pit`：除权事件只在生效日和已知日都到达后才进入序列，未来同步不会回写旧快照。没有事件文件时会从供应商 `adj_factor` 推导增量，但 provider 的 `point_in_time` 会标记为 `false`，TY-Factors 默认拒绝该降级口径。

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

`TushareConfig` 只保存 `token_source=environment`、环境变量名（默认 `TUSHARE_TOKEN`）和重试次数，不接受 token 文本。`TushareDailyFetch` 分别调用 `daily` 和 `adj_factor`，可选调用 `dividend`，再按 `ts_code + trade_date` 合并。股票代码支持逗号、分号或换行分隔。每个 raw 快照写入 `manifest.json`、`raw.parquet`，有事件时另写 `events.parquet`；同一目录出现新 snapshot 会自动写入 `<snapshot_id>` 子目录，不覆盖历史版本。`TushareConfig` 只负责凭证，查询参数由 `QlibControl` 管理，token 永远不会进入总控句柄或工作流。

`TushareToQlib` 的 `adjustment_policy` 有四种：`pit`（推荐，事件驱动）、`vendor_qfq`、`vendor_hfq` 和 `none`。`none` 只适合检查原始数据，因子计算会拒绝它。`TYFactorCompute` 默认加载版本化的 `TY-Factors` 注册表，当前包含动量、波动率和成交量比率；选择 `alpha158` 时直接使用 Qlib 的 158 个标准公式，前提是 provider 已经是复权后的标准字段。`selected` 可从两套注册表选因子，`custom` 接受 JSON 因子定义。

动量因子采用统一定义：`当前 ty_close / N 日前 ty_close - 1`；预热不足或回看价格为零时保留 NaN，并在质量报告中计数。这样未来复权事件不会改变已经提交的旧 snapshot，因子方向也与常见量化研究口径一致。

`QlibDataset.label_horizon=0` 表示按因子集自动选择标签窗口：`TY-Factors` 使用下一交易日收益，Alpha158 使用 Qlib 默认的 T+1 到 T+2 收益；填入 1-252 可以显式覆盖。

## 接入本地 ComfyUI

本地 ComfyUI 目录为 `E:\ComfyUI_windows_portable-G314\ComfyUI`。独立测试通过后建立 junction，不复制源码：

```powershell
cmd /c mklink /J "E:\ComfyUI_windows_portable-G314\ComfyUI\custom_nodes\ty-quant-node" "D:\work_station\ty-comfyui-node\ty-quant-node"
```

重启 ComfyUI 后端，搜索 `TY Quant` 节点；修改 Python 后重新启动后端，修改前端资源后刷新浏览器。示例 workflow 位于 `examples/mvp_workflow.json`（本地 CSV）和 `examples/ty_factors_workflow.json`（Tushare→PIT→TY-Factors），固定输入位于 `tests/fixtures/market.csv`。工作流使用完整 ComfyUI 0.4 编辑器格式；本地安装副本位于 `E:\ComfyUI_windows_portable-G314\ComfyUI\user\default\workflows\ty-qlib\`。

节点只访问本地白名单路径。默认白名单包括 ComfyUI 当前工作目录和节点仓库；行情文件或 artifact 放在其他目录时，在启动 ComfyUI 的进程环境中追加根目录：

```powershell
$env:TY_QUANT_ALLOWED_ROOTS = "D:\\quant-data;D:\\quant-artifacts"
```

路径中的 URL、设备路径和 `..` 穿越会在节点读取前直接拒绝。句柄携带的路径也会重新校验，不能通过手工修改 workflow 绕过白名单。

工作流结构由 `src/ty_quant_node/workflow.py` 生成和校验。独立验证使用 `uv run pytest ty-quant-node/tests -q`；本地 CSV 联调将生成 `.artifacts/comfyui-mvp/provider`、`.artifacts/comfyui-mvp/model` 和 `.artifacts/comfyui-mvp/report/equity.png`，Tushare 工作流以 `QlibControl` 为总控并使用 `.artifacts/ty-factors-mvp/` 下的 snapshot、provider、factors、model 和 report 子目录。

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

首版面向本地 Windows ComfyUI 和日频研究。它不提交券商订单、不提供远程多用户服务，也不加载未知 pickle。滚动训练、风险模型和更丰富的前端展示作为后续独立版本。
