# 变更记录

## 未发布

- Tushare 日线、复权因子和事件请求支持按股票与日期窗口分块，并对空结果、重复键、缺失/非正复权因子和异常响应给出明确错误。
- `TushareConfig` 增加请求分块大小配置，避免大股票池和长区间触发单次接口限制。
- `QlibDataset` 从已导出的 provider 直接使用调整后 `close` 生成标签，避免复权日跨段收益回到 raw 价格口径。
- `QlibControl` 扩展为 Tushare/PIT/TY-Factors/训练回测统一总控，两个示例工作流均从 canonical builder 生成。
- 增加统一 artifact 事务：raw snapshot、Qlib provider、因子、模型、回测和报告使用 staging 目录原子发布。
- 增加运行键和 manifest：相同输入复用版本，输入或参数变化写入新的 hash 子目录。
- 修正 `TY_MOM_5` 与 `TY_MOM_20` 的方向为“当前价格 / 回看价格 - 1”。
- 空复权事件列表按恒等复权处理，回看价格为零时因子输出 NaN。
- 为独立安装补充基础依赖，并把 Qlib、LightGBM 放入可选 extras。
