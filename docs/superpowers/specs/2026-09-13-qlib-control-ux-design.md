# QlibControl 总控节点交互重构设计

## 目标

将 `QlibControl` 从“所有模块参数平铺”的调试型节点重构为面向日常研究的配置面板：用户能先选择数据源，再按模块填写必要参数；路径、日期和 JSON 配置使用适合各自语义的控件；节点仍输出一个 `QLIB_CONTROL` 句柄供后续节点使用。

本版直接升级配置契约，不保留旧工作流兼容。旧的 `mvp_workflow.json` 和 `ty_factors_workflow.json` 将重新生成，旧字段不再出现在新的节点输入定义中。

## 当前问题与取舍

- 本地 CSV 的 `adjustment` 与 Tushare 的 `adjustment_policy` 语义重叠，统一为 `adjustment_mode`。
- 五个输出目录字段合并为一个 `artifact_root`，节点按固定子目录派生：`provider`、`snapshots`、`factors`、`model`、`report`。
- CSV 路径和 Tushare 查询参数属于互斥数据源，增加 `data_source` 选择，不再让用户同时面对两套入口。
- 训练/测试区间和 Tushare 查询区间都保留，但通过统一的日期范围控件展示，内部字段分别叫 `query_start/query_end`、`train_start/train_end`、`test_start/test_end`。
- JSON 参数保留能力，但默认放进“高级设置”区域，并给出 JSON 结构示例和中文说明。

## 新配置契约

`QlibControl.INPUT_TYPES` 的 visible widget 按以下顺序组织：

### 数据源

- `data_source`: `local_csv` 或 `tushare`，默认 `tushare`。
- `csv_path`: 本地 CSV/Parquet 路径；只在 `local_csv` 模式显示。
- `ts_codes`: Tushare 股票代码，多代码可用逗号、分号或换行分隔；只在 `tushare` 模式显示。
- `query_start`、`query_end`: Tushare 查询日期范围；只在 `tushare` 模式显示。

### 复权与数据维护

- `adjustment_mode`: `pit`、`vendor_qfq`、`vendor_hfq`、`raw`。
- `include_events`: 是否同步分红/送转事件，默认开启；仅 Tushare 模式有意义。
- `incremental`: 是否复用已有快照和 provider，默认开启。

### 训练与测试

- `train_start`、`train_end`: 训练日期范围，可留空表示由 Dataset 后端使用全部可用区间。
- `test_start`、`test_end`: 测试日期范围，可留空表示使用默认测试段。

### 因子

- `factor_set`: `ty_factors`、`alpha158`、`selected`、`custom`。
- `selected_json`、`custom_json`: 高级 JSON 输入，默认收起。

### 模型与回测

- `model_type`: `linear` 或 `lightgbm`。
- `params_json`: 模型参数 JSON，默认收起。
- `segment`: 预测段。
- `topk`、`n_drop`、`transaction_cost_bps`: 回测参数。

### 产物目录

- `artifact_root`: 统一产物根目录，默认 `outputs/ty_quant`。

句柄 metadata 使用上述新字段，并增加 `config_schema_version: "2"`。下游节点读取新字段；没有旧字段回退分支。

## 交互设计

### 区域和条件显示

Python 输入定义提供每个字段的中文 `tooltip`。前端扩展只对 `QlibControl` 生效，在节点中渲染六个区域标题和轻量分隔线。`data_source` 改变时，CSV/Tushare 专属字段即时显示或隐藏；隐藏字段的值仍保留在工作流序列化中，切换模式不会丢失用户上次填写内容。

### 路径选择器

`csv_path` 和 `artifact_root` 使用文本框加“选择目录/文件”按钮。按钮调用节点自己的安全目录接口：

- `GET /ty-quant-node/fs/roots` 返回当前白名单根目录。
- `GET /ty-quant-node/fs/list?path=<path>` 返回当前目录的子目录和文件。
- 服务端复用 `configured_allowed_roots()` 和 `resolve_allowed_path()`，禁止 URL、设备路径、`..` 穿越和白名单外访问。
- 目录浏览器只显示白名单内内容，选择后回填绝对路径；后端执行时仍再次校验。

CSV 路径选择器显示 `.csv`、`.parquet` 文件；`artifact_root` 选择器只选择目录。浏览器关闭或取消不改变原值。

### 日期控件

三个日期范围使用相同的范围控件：开始日期和结束日期并排显示，输入框支持浏览器日历弹出、键盘输入和清空。序列化仍使用 `YYYY-MM-DD` 字符串。控件在前端做即时检查，后端 `QlibControl.run` 做最终检查：开始日期不能晚于结束日期，训练结束必须早于测试开始；Tushare 查询日期必须成对出现。

### 错误反馈

字段级错误在节点执行前以中文提示；目录接口错误显示“路径不在允许目录内”等可操作信息。后端异常继续使用现有 ComfyUI 节点错误通道，不把 token 或其他凭证写入 UI、日志和 metadata。

## 实现边界

- 新增 `web/ty_quant_control.js`，通过 `WEB_DIRECTORY` 注册 ComfyUI 扩展；不修改 ComfyUI 本体。
- 新增轻量服务器模块注册上述三个只读目录接口；没有 token、网络请求或数据库依赖。
- `workflow.py` 的 builder、validator 和 API prompt 转换器全部改用 schema v2 字段。
- 旧工作流文件删除后重新生成，示例路径保持不变。
- 下游节点的计算算法、句柄类型和 artifact 完整性链保持不变，只更新读取的控制字段名。

## 验收标准

1. `QlibControl` 只显示新契约字段，六个区域顺序稳定，重复入口消失。
2. 每个 visible widget 在 `/object_info/QlibControl` 中带中文 tooltip。
3. 切换 `data_source` 时，CSV/Tushare 字段即时隐藏和恢复。
4. 路径按钮只能浏览和选择白名单目录/文件，越界请求被拒绝。
5. 三组日期范围支持日历选择、键盘输入、清空和实时顺序提示。
6. 新版 Tushare 工作流与本地 CSV 工作流均能通过 `/prompt` 执行完整 MVP。
7. 固定 fixture 测试、工作流 schema 测试、目录接口测试和 ComfyUI 8190 联调全部通过。
