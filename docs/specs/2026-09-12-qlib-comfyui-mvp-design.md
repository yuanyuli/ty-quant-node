# Qlib ComfyUI 节点组 MVP 设计规格

## 背景与目标

在 `D:\work_station\ty-comfyui-node` 下新增独立仓库 `ty-quant-node`，把 Qlib 的离线量化研究闭环映射为 ComfyUI 节点图。MVP 的验收闭环是：固定 CSV fixture → DatasetH → LightGBM/Linear 训练 → 预测信号 → TopK/Dropout 回测 → 指标与净值曲线输出。

现有 Civitai 节点提供参考：独立仓库、ComfyUI 注册映射、客户端与业务逻辑分离、缓存、离线 fixture、清晰错误信息和前端结果展示。Qlib 源码调研确认其稳定边界为 DataHandler/DatasetH、BaseModel fit/predict、SignalRecord/PortAnaRecord 和 R 实验记录器。

## 范围与非目标

MVP 支持本地 CSV/Parquet 数据、Qlib DatasetH、LightGBM 与 Linear 模型、预测、TopK/Dropout 回测、JSON/表格/PNG 结果和本地实验记录。首版不接实时行情、券商订单、远程服务、多用户权限、LLM 因子生成或完整 qrun YAML 编辑器。

## 仓库与运行边界

仓库路径为 `D:\work_station\ty-comfyui-node\ty-quant-node`，必须拥有独立 Git 历史、README、许可证、测试和 ComfyUI `__init__.py`。不得导入 `civitai-inspiration` 或父项目运行时代码；共享仅限父目录 uv 环境。Qlib 作为明确依赖安装到该环境，ComfyUI 通过 junction 接入 `custom_nodes`。

## 节点与数据契约

1. `QlibRuntime`：输入 provider_uri、region、experiment_uri、seed；输出 `QLIB_RUNTIME`。初始化一次 Qlib，校验路径位于允许目录，并设置随机种子。
2. `QlibDataset`：输入 runtime、数据文件、instruments、字段表达式、label 表达式、train/valid/test 日期；输出 `QLIB_DATASET`，句柄只含配置、数据路径和 schema，不序列化大型 DataFrame。
3. `QlibModel`：输入 runtime、model_type（`lightgbm`/`linear`）、参数 JSON；输出 `QLIB_MODEL_SPEC`。
4. `QlibTrain`：输入 dataset、model spec、experiment_name；执行 fit，输出 `QLIB_TRAINED_MODEL`、`QLIB_TRAIN_SUMMARY`、recorder id。
5. `QlibPredict`：输入 trained model、dataset、segment；输出 `QLIB_SIGNAL_TABLE`，至少包含 instrument、datetime、score。
6. `QlibBacktest`：输入 signal table、dataset/runtime、topk、n_drop、成本参数；输出 `QLIB_BACKTEST_RESULT`，包含指标字典、净值 DataFrame/CSV 和曲线 PNG 路径。
7. `QlibReport`：输入 backtest result；输出 ComfyUI 可消费的 `STRING` JSON、`IMAGE` 曲线和摘要文本。

公共句柄使用版本化 dataclass，包含 `kind`、`version`、`path`、`created_at`、`metadata`；路径不可越过 runtime 白名单。节点错误统一转换为带节点名、参数名和修复建议的 RuntimeError。

## 数据流与缓存

节点执行采用显式句柄流。训练、预测和回测结果写入仓库私有 `.cache/qlib`，缓存键由规范化配置、输入文件 sha256、Qlib 版本和节点版本组成。缓存命中前校验文件存在和 schema；`refresh` 强制重算。workflow JSON 只保存配置与句柄元数据，不保存模型二进制和大表。

## 安全、可复现与兼容性

仅允许白名单目录下的本地数据和输出路径；拒绝 `..` 穿越、设备路径和任意 URL。模型加载使用 Qlib 的受限反序列化路径，不执行未知 pickle。默认 seed 固定为 42，并在摘要中记录 Python、Qlib、模型版本和输入 hash。首版支持 Windows 本地 ComfyUI 与父目录 uv 环境；无网络依赖即可运行 fixture 测试。

## 结果展示

回测结果至少包含累计收益、年化收益、最大回撤、Sharpe（数据不足时为 null）、IC/RankIC（可计算时）和交易次数。`QlibReport` 生成单张 RGB 净值曲线 PNG 及 JSON 摘要；长任务不阻塞前端额外 API，遵循 ComfyUI 节点执行模型。

## ty-quant 集成策略

已调研 `yuanyuli/ty-quant`：其为基于 Qlib + RD-Agent 的 FastAPI/React 平台，包含数据源插件、Tushare、HDF5 缓存、数据质量检查、因子与回测服务；ComfyUI MVP 复用其协议和数据口径，但不依赖其 Web/API 运行时。内部定义 `QuantBackend` 协议，包含 `build_dataset`、`train`、`predict`、`backtest` 四个方法；默认实现 `QlibBackend`。未来获得 ty-quant 源码后，只需新增适配器和配置，不改变节点契约。

## 测试与验收

测试全部使用固定小型 CSV fixture 和临时目录：节点注册与 INPUT_TYPES；路径/参数校验；句柄 JSON 往返；DatasetH 构建；LightGBM/Linear 训练与预测形状；回测指标边界（空信号、单日、缺失值）；缓存命中与失效；报告 PNG 生成。验收命令为 `uv run pytest ty-quant-node/tests -q`，并在真实 ComfyUI 重启后确认节点可搜索且示例 workflow 可执行。

## 版本与后续演进

MVP 版本 `0.1.0`。后续按独立变更增加 Alpha158 特征模板、更多模型、滚动训练、风险模型、交互式前端和 ty-quant 适配器；每项保持独立节点/句柄边界。

## 数据源与复权修订（v1.1）

### ty-quant 调研结论

`yuanyuli/ty-quant` 是基于 Qlib + RD-Agent 的 FastAPI/React 量化研究平台，已有数据源适配器、插件注册、HDF5 缓存、数据质量检查、因子评估和回测服务。可复用的边界是 `BaseDataSource`、`TushareDataSource`、数据版本 bundle、`QuantBackend` 思路和 data-to-qlib 的 calendar/instruments/features 一致性校验；ComfyUI 节点不依赖其 FastAPI、Celery、Redis 或数据库运行时。

### Tushare 数据合同

新增 `TushareDailySource`，凭证只从 `TUSHARE_TOKEN` 环境变量或 ComfyUI 服务器配置读取，不进入 workflow、日志和缓存键。日线通过 `pro.daily` 获取原始 OHLCV，复权因子通过 `pro.adj_factor` 单独获取；股票列表通过 `pro.stock_basic`，可选估值通过 `daily_basic`。接口失败必须区分“无数据”和“认证/网络错误”，重试网络错误 3 次并给出中文错误。

### 原始数据与复权数据双轨保存

每个交易日、股票记录同时保存：`open_raw/high_raw/low_raw/close_raw/volume_raw/amount_raw`、`adj_factor`、`trade_status`、`source`、`asof`。原始字段永不覆盖；派生字段按请求的 `adjustment` 计算：`none` 使用 raw，`qfq` 为 `raw_price * adj_factor / anchor_factor`，`hfq` 为 `raw_price * adj_factor`。MVP 的 anchor 为查询区间最后一个有效复权因子，并在数据清单记录 anchor 日期，避免不同查询区间产生不可追溯的价格。

成交量使用反向比例调整：`volume_adj = volume_raw * anchor_factor / adj_factor`；金额保持原始口径。复权仅作用于价格与成交量，不对 `adj_factor` 再次复权。缺失或非正因子不得静默填 1：默认标记该行质量错误并阻止进入训练/回测，只有用户显式选择 `allow_unadjusted=true` 才能降级为 none。

### Qlib 导出约定

导出前先完成 calendar、instruments、features 三方校验；calendar 严格升序，features 每个 bin 长度与 calendar 一致，instruments 与 features 目录集合一致。Qlib feature 至少写入 `$open/$high/$low/$close/$volume/$factor`，并将所选 adjustment、数据版本和因子 anchor 写入 manifest。默认训练/回测使用 `qfq`，原始价格仅用于审计；回测成交价、涨跌停和收益计算必须使用同一 adjustment 版本。

### 数据节点调整

MVP 节点增加：`TushareConfig`（token 来源、限速、重试）、`TushareDailyFetch`（股票池、日期、raw+factor）、`AdjustPrices`（none/qfq/hfq、anchor）、`QlibExport`（导出与一致性报告）。原 `QlibDataset` 改为消费 `QlibExport` 句柄，禁止直接把未声明复权口径的 CSV 当作训练数据。

### 增量与版本化

缓存按 `source + ts_code + date_range + raw_hash + factor_hash` 分片；收盘后增量拉取，因历史分红导致因子变化时自动重建受影响股票的完整区间。每日生成 manifest，包含 source、pulled_at、date range、row count、raw/factor checksum、adjustment 和 quality errors；回测必须绑定 manifest 版本以保证可复现。

### 新增验收

固定 fixture 必须包含一次分红导致 adj_factor 变化的股票，验证 qfq close 连续、raw close 保留、volume 反向调整、anchor 写入 manifest、缺失因子阻止训练、Tushare API 使用 token 且不泄漏。另加导出后 calendar/bin/instruments 三方一致性测试。


