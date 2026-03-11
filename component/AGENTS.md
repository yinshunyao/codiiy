# component 目录说明

`component` 是控制层统一入口，负责对各子模块能力进行组织、路由与调用约束。

核心职责：
- 统一函数调用入口，支持按 `function_path` 字符串进行分发调用。
- 在调用前执行组件启停校验，确保被停用组件不会被误调用。
- 维护组件注册索引与运行时状态，作为控制层能力治理基础。

关键入口函数（见 `component/README.json`）：
- `component.call_by_path`
- `component.resolve_function`
- `component.list_components`
- `component.get_component_enabled`
- `component.set_component_enabled`

## 模块边界要求

`component` 下按能力域划分模块，当前至少包含：
- `component/observe`：观察与感知能力
- `component/handle`：执行与处理能力
- `component/communicate`：沟通能力

新增模块必须保持以下原则：
- 目录命名清晰稳定，与能力域一致。
- 不破坏既有模块职责边界。
- 模块文档与索引同步更新，避免“有代码无登记”。

## 组件化要求

`component` 及其子目录必须按“组件”组织能力，禁止散落函数长期无归属维护。

组件组织规范：
- 组件目录采用 `component/<module>/<component_name>`。
- 每个组件独立目录，支持独立新增、独立升级、独立维护依赖。
- 不同组件之间禁止隐式耦合，公共能力需通过稳定接口调用。

注册与状态规范：
- 组件注册索引：`component/component_index.json`
- 组件状态文件：`component/component_state.json`
- `function_path -> component_key` 映射必须完整，避免运行时定位不一致。

文档同步规范：
- `component/README.json`：维护控制层整体说明、关键函数、子目录边界。
- `component/<module>/README.json`：维护模块内组件、函数、输入输出、备注。
- 新增/变更组件时，代码与 README/索引必须同批次更新。

## 参数规范（必须遵循）

组件参数统一分为两层，禁止混用：

- **系统参数（System Params）**：组件级共享参数，例如 `api_key`、`webhook_url`、`secret`。
- **API 参数（API Params）**：单次 API 调用参数，例如 `text`、`prompt`、`model`、`json_mode`。

### 系统参数规范

- 每个组件都必须在模块 `README.json` 的 `components` 中声明 `system_param_schema`：
  - 有系统参数：`enabled=true` + `fields`。
  - 无系统参数：也必须显式声明 `enabled=false`、`fields=[]`。
- 系统参数由组件配置页统一维护，敏感字段必须标记 `sensitive=true`。

### API 参数规范（demo / 测试页）

- 每个 API 必须声明 `demo_param_schema`，字段结构参考 `system_param_schema.fields`，并增加 `value_type`：
  - 允许值：`string` / `int` / `float` / `bool` / `json`。
- demo 参数默认归属 API 级参数，不落库，不写入系统参数配置。
- 测试页按 `demo_param_schema` 自动渲染输入项并执行类型转换、必填校验。

### 函数签名兼容规范

- 测试页会对“非必填且留空”的参数不传值。
- 因此：凡在 `demo_param_schema` 中为非必填的参数，函数签名必须可省略（提供默认值），避免 `missing required positional argument`。
- 运行时必填约束应通过业务校验返回清晰错误，而不是依赖 Python 签名异常。

## 测试页面规范（Demo Runner）

- 组件功能页中的 API 应提供“测试 API”入口。
- 测试页统一通过 `component.call_by_path(function_path, kwargs)` 执行调用。
- 页面需展示：
  - 组件信息与 API 路径。
  - 系统参数配置入口（若该组件启用系统参数）。
  - 本次调用入参与测试结果（结构化 JSON，结果区可滚动）。

兼容与升级规范：
- 不提供隐式旧路径别名兼容。
- 仅支持 README 与组件索引中登记的规范函数路径。
- 组件升级应最小化影响范围，避免非目标组件被连带修改。

## 工具依赖约束

- 工具调用时必须先根据 `function_path` 映射到组件目录。
- 依赖检查以组件目录内 `requirements.txt` 为准。
- 调用工具目录不单独维护重复依赖清单。

## 开发执行要求

- 任何 component 相关需求，先检查并更新设计文档，再修改代码实现。
- 优先复用既有实现，避免重复开发与能力分叉。
- 变更必须保持与现有工程结构一致，保证可集成、可迁移、可复用。
