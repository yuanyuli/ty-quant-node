# TY-Factors 数据节点与因子计算设计

## 目标

在 `ty-quant-node` 独立仓库中增加可复现的 Tushare 数据同步、point-in-time 复权、Qlib 转换和 `TY-Factors` 因子计算能力，并打磨现有节点的输入输出契约。因子在日期 `t` 的值只使用 `t` 当时可用的数据和复权事件，不因未来日期新增事件而静默改写。

## 关键决策

1. 原始日线和复权事件分层保存，原始层不可覆盖。
2. 默认因子口径为 point-in-time（简称 PIT），不直接使用供应商的“今天回看历史”的最终 qfq 序列。
3. Qlib provider 同时保存原始字段、PIT 复权字段、归一化 factor 和 manifest；标准 Alpha158 作为可选 benchmark，`TY-Factors` 作为默认扩展。
4. 不在 158 条 Alpha158 字符串上做散乱替换。因子表达式引用统一的 `ty_*` 字段；字段由数据转换层一次生成，避免 `Ref` 与 factor 日期错位。
5. 数据变更采用版本化快照。只新增日期且历史因子 hash 不变时增量追加；单个标的历史因子变化时只重建该标的；旧版本不覆盖。

## 数据语义

### 原始字段

`TushareDailyFetch` 输出 `MARKET_DATA` 句柄，产物包含：

- `instrument`、`datetime`
- `open_raw`、`high_raw`、`low_raw`、`close_raw`、`volume_raw`、`amount_raw`
- `adj_factor`（供应商原始累计复权因子）
- `trade_status`、`source`、`asof`
- 分红送转事件及 `knowledge_date`（启用 `include_events` 时）

### PIT 复权字段

转换层从事件和快照生成以下字段：

```text
ty_price_factor(t) = 截止 t 已生效且在快照中可用的价格/总收益事件累积值
ty_split_factor(t) = 截止 t 已生效的拆分送转事件累积值
ty_close(t) = close_raw(t) * ty_price_factor(t)
ty_open/high/low(t) = raw * ty_split_factor(t)
ty_volume(t) = volume_raw(t) / ty_split_factor(t)
```

现金分红只影响 `ty_price_factor`，不反向调整成交量。事件的激活日为 `max(effective_date, knowledge_date)`：公告早于除权日时在除权日生效，供应商晚到事件时不会提前泄露。若供应商只有 `adj_factor` 而没有事件日期，MVP 允许生成 vendor snapshot 版本，但 manifest 必须标记 `point_in_time=false`，不能把它伪装成 PIT 结果。

### Qlib provider 兼容层

为兼容 Qlib 标准 DataHandler，provider 的标准字段 `$open/$high/$low/$close/$volume/$vwap` 默认映射到 PIT 复权字段；`$factor` 映射为“调整价格/原始价格”的归一化 factor。原始字段和供应商 factor 保存在 `dataset.parquet`，用于审计。`none` 模式下 `$factor=1.0`。

## 节点契约

### `TushareConfig`

只保存 `token_source=environment`、token 环境变量名和请求重试次数；token 只从 ComfyUI 进程环境读取，不能进入句柄 metadata、workflow、日志和 artifact。

### `TushareDailyFetch`

输入：`TUSHARE_CONFIG`、逗号/分号/换行分隔股票代码、起止日期、缓存/快照目录，以及可选的 `include_events`。

输出：`MARKET_DATA`，路径指向 raw parquet 和事件快照 manifest，不直接输出 Qlib `.bin`。默认拉取 `daily`、`adj_factor`，支持可选的分红送转接口；日线和 factor 按 `instrument + datetime` 一对一校验。

### `TushareToQlib`

输入：`MARKET_DATA`。

参数：`adjustment_policy`（`pit`、`vendor_qfq`、`vendor_hfq`、`none`）、anchor/版本策略、输出目录、是否增量。

输出：`QLIB_EXPORT`，包含 `calendars/day.txt`、`instruments/all.txt`、标准及 `ty_*` features、`dataset.parquet`、`manifest.json`。

### `TYFactorCompute`

输入：`QLIB_EXPORT`。

参数：`factor_set`（`ty_factors`、`alpha158`、`selected`、`custom`）、因子选择 JSON、表达式 JSON、预热窗口、输出目录。

输出：`QLIB_FEATURE_SET`，包含 feature parquet、因子清单、表达式版本、输入 provider 版本和质量报告。

`ty_factors` 的每个因子使用 `factors/<category>/<name>.yaml` 描述，至少包含 `name`、`version`、`expression`、`inputs`、`lookback`、`adjustment_policy`、`null_policy`。第一批内置因子包括 `TY_MOM_5`、`TY_MOM_20`、`TY_VOL_20` 和 `TY_VOLUME_RATIO_20`，公式引用 `ty_close`、`ty_volume` 等 PIT 字段。

动量公式固定为 `$ty_close / Ref($ty_close, N) - 1`。兼容计算路径与 Qlib 表达式保持同向；回看价格为零时生成 NaN，不能生成无穷值。

## Alpha158 口径

加载 Qlib `Alpha158DL.get_feature_config()` 的完整定义作为 benchmark，不修改原始表达式。Alpha158 模式必须使用 PIT provider 的标准复权字段，并采用 Qlib 默认标签 `Ref($close, -2) / Ref($close, -1) - 1`；自定义 TY 因子可配置 horizon，但不得使用未来复权事件。

## 增量与稳定性

每次同步保存 `raw_hash`、`factor_hash`、`events_hash`、`snapshot_id` 和 `asof`。同一目录出现不同 snapshot 时写入 `<snapshot_id>` 子目录；缓存命中条件是输入快照、因子集合、表达式版本和 Qlib 版本全部一致。历史事件被供应商修订时生成新 provider 版本，旧版本仍可用于复现旧回测。

### 产物提交与重复运行

raw snapshot、Qlib provider、因子特征集、训练模型、回测结果和报告均使用同级 staging 目录构建，再通过原子目录替换提交。目标已经存在时不得覆盖；节点根据输入内容和参数计算运行键，相同运行键复用已有 manifest，运行键变化则写入新的短 hash 子目录。任何写入异常都必须删除 staging，不能留下缺少 manifest 的半成品目录。模型、回测和报告 manifest 还要记录各自的运行键及上游摘要，以便在 ComfyUI 中重复执行时得到确定的句柄路径。

## 验收标准

- Tushare fake server 能验证 daily/factor/event 合并、token 不泄漏和错误分类。
- PIT 复权在未来新增事件后不改变过去已发布日期的 `ty_close` 和 `TY_MOM_20`。
- vendor qfq 模式明确标记非 PIT，并校验归一化 `$factor` 语义。
- Qlib provider 的 calendar、instruments、features 一致，`$vwap` 可被 Alpha158 读取。
- 完整 Alpha158 能计算；TY-Factors 能按 YAML 注册、选择、缓存和输出质量报告。
- 所有现有 28 个测试保持通过，并新增节点契约、稳定性、Alpha158 和增量重建测试。
