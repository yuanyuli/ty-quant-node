# 变更记录

## 未发布

- 增加统一 artifact 事务：raw snapshot、Qlib provider、因子、模型、回测和报告使用 staging 目录原子发布。
- 增加运行键和 manifest：相同输入复用版本，输入或参数变化写入新的 hash 子目录。
- 修正 `TY_MOM_5` 与 `TY_MOM_20` 的方向为“当前价格 / 回看价格 - 1”。
- 空复权事件列表按恒等复权处理，回看价格为零时因子输出 NaN。
- 为独立安装补充基础依赖，并把 Qlib、LightGBM 放入可选 extras。
