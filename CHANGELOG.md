# 变更记录

## 未发布

- `QlibControl` 增加枚举、日期窗口、`n_drop/topk`、交易成本和 JSON 配置的入口校验，避免无效参数流入下游节点。
- ComfyUI 注册增加 14 个稳定中文 display name，保留英文 node key 以兼容已有工作流。
- 预测信号改为按运行键写入 `signals/<run_key>/signal.parquet`，新增输入引用、列契约和文件 SHA-256 manifest；相同运行键校验后复用，冲突产物拒绝覆盖。
- `QlibRuntime` 在真实 Qlib 和兼容后端分支统一初始化 Python 与 NumPy 随机种子。
- 增加通用 manifest 文件完整性校验；模型加载、回测和报告在消费前验证 SHA-256，拒绝被篡改的模型、信号、指标和净值曲线。
- 兼容升级前缺少 `files.model` 的简化模型缓存；完整新 manifest 继续强制校验。
- Tushare 日线、复权因子和事件请求支持按股票与日期窗口分块，并对空结果、重复键、缺失/非正复权因子和异常响应给出明确错误。
- `TushareConfig` 增加请求分块大小配置，避免大股票池和长区间触发单次接口限制。
- `QlibDataset` 从已导出的 provider 直接使用调整后 `close` 生成标签，避免复权日跨段收益回到 raw 价格口径。
- `QlibControl` 扩展为 Tushare/PIT/TY-Factors/训练回测统一总控，两个示例工作流均从 canonical builder 生成。
- 增加统一 artifact 事务：raw snapshot、Qlib provider、因子、模型、回测和报告使用 staging 目录原子发布。
- 增加运行键和 manifest：相同输入复用版本，输入或参数变化写入新的 hash 子目录。
- 修正 `TY_MOM_5` 与 `TY_MOM_20` 的方向为“当前价格 / 回看价格 - 1”。
- 空复权事件列表按恒等复权处理，回看价格为零时因子输出 NaN。
- 为独立安装补充基础依赖，并把 Qlib、LightGBM 放入可选 extras。
