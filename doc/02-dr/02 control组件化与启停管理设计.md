# component 组件化与启停管理设计

## 1. 设计目标
1. 建立 `component` 统一组件目录标准，支持组件独立新增与升级。
2. 在不破坏现有调用方式的前提下，引入升级兼容映射能力。
3. 为 `component.call_by_path` 增加组件启用/停用校验，支持快速隔离故障组件。
4. 保持工具层（如 `tools/control_call_tool`）对新机制透明可用。
5. 将 `tools/file_reader` 按组件标准迁移到 `component/handle/file_reader_component`，作为 `handle` 模块首个组件能力。

## 2. 设计范围
1. `component`（组件）目录与调用链改造。
2. `component/observe` 组件化落地（作为首个示例模块）。
3. `component/handle/file_reader_component` 组件化落地（文件读取与检索能力）。
4. `component/communicate` 组件化落地（钉钉/企业微信/飞书通信能力）。
5. 通信组件参数配置方案：显式传参 + Django 数据库存储读取。
6. 组件注册索引、兼容映射、组件状态持久化能力。
7. `component/README.json`、`component/observe/README.json`、`component/handle/README.json`、`component/communicate/README.json` 的结构补充。

## 3. 组件目录标准
### 3.1 标准结构
以 `component/<module>` 为能力模块根目录，组件目录直接放在模块下一层：

`component/<module>/<component_name>/`

每个组件目录建议包含：
1. `__init__.py`：组件导出 API。
2. `api.py` 或业务实现文件：组件核心逻辑。
3. `requirements.txt`：组件依赖声明。
4. `README.md`：组件自述与使用说明。
5. 可选资源文件：该组件独有配置与说明。

### 3.2 observe 模块改造策略
1. 将现有截图与理解能力迁移到 `component/observe/*_component`。
2. 将 `component/observe/qwen2vl_vllm.py` 移入屏幕理解组件目录，避免模块外层散落实现。
3. 组件依赖与自述拆分到各自组件目录下，不再维护模块级 `requirements.txt`。
4. `component/observe/__init__.py` 直接从组件目录导出规范 API，不再保留模块级兼容转发文件。
5. 组件调用与扩展统一以“组件目录 + 模块 `__init__.py` 导出 + `README.json` 登记路径”为准。

### 3.3 handle 模块首个组件落地策略（file_reader）
1. 将 `tools/file_reader` 核心能力迁移至 `component/handle/file_reader_component`。
2. 新组件目录遵循标准结构，至少包含：
   - `component/handle/file_reader_component/__init__.py`
   - `component/handle/file_reader_component/api.py`
   - `component/handle/file_reader_component/requirements.txt`
   - `component/handle/file_reader_component/README.md`
3. 对外导出规范函数路径：
   - `component.handle.read_file`
   - `component.handle.read_lines`
   - `component.handle.search_keyword`
   - `component.handle.search_regex`
   - `component.handle.get_file_stats`
   - `component.handle.get_system_info`
4. 旧工具目录可保留轻量适配壳用于平滑过渡，但组件调用与后续扩展以 `component.handle.*` 为唯一规范路径。

### 3.4 communicate 模块三方通信组件落地策略
1. 新增 `component/communicate` 模块目录，并按通信平台拆分为三个独立组件目录：
   - `component/communicate/dingtalk_component`
   - `component/communicate/wecom_component`
   - `component/communicate/feishu_component`
2. 每个组件目录至少包含：
   - `__init__.py`
   - `api.py`
   - `requirements.txt`
   - `README.md`
3. 对外导出规范函数路径：
   - `component.communicate.send_dingtalk_text`
   - `component.communicate.send_wecom_text`
   - `component.communicate.send_feishu_text`
4. 各通信组件仅负责自身平台协议拼装与请求发送，不允许跨组件共享内部私有实现。
5. `component/communicate/README.json` 明确组件待配置参数清单，供 Django 平台读取与配置。

## 4. 通信组件参数配置设计
### 4.1 配置来源与优先级
通信组件支持两类配置来源，按以下优先级解析：
1. 显式传参（函数参数中的 `webhook_url`、`key`、`secret`、`app_id` 等）。
2. Django 数据库存储配置（通过 `config_name` + `provider` 查询）。

若两者均不存在，则抛出明确异常，禁止静默降级到硬编码或不安全默认值。

### 4.2 Django 配置模型
在 `core/collector` 中新增通信配置模型（ORM）：
1. `provider`：通信平台标识（dingtalk / wecom / feishu）。
2. `name`：配置名称（同一平台内唯一），用于组件通过 `config_name` 查找。
3. `display_name`：页面展示名。
4. `is_enabled`：配置是否启用。
5. `config`：JSON 字段，存储平台所需参数键值（如 webhook_url、secret、app_key 等）。
6. `description`：可选说明。

通过 Django Admin 维护该模型，实现“界面配置 + 数据库存储”能力。

### 4.3 组件读取规则
1. 组件通过统一解析函数读取配置，输出结构化结果。
2. 当传入 `config_name` 且 Django 运行环境可用时，按 `provider + config_name` 查询启用配置。
3. 查询不到或配置缺键时，返回明确错误（包含缺失字段名）。
4. 组件层只读取必要参数，不持久化、不打印敏感值。

## 5. 组件系统参数通用机制设计
### 5.1 组件参数 Schema 规则
组件如需平台配置系统参数，必须在对应模块 `README.json` 的组件定义中声明：
1. `system_param_schema.enabled`：是否启用系统参数配置。
2. `system_param_schema.fields`：字段清单，字段项包含：
   - `name`：参数名（组件运行时读取 key）；
   - `required`：是否必填；
   - `sensitive`：是否敏感字段（如 key/secret/token）；
   - `description`：字段说明；
   - `default`：可选默认值。
3. 参数名与字段集合不做平台硬编码，完全由组件 Schema 驱动，支持后续扩展。

### 5.2 Django 页面联动规则
1. 组件功能查询页读取模块 `README.json`。
2. 若组件存在以下任一能力，则展示“组件配置”按钮：
   - `system_param_schema.enabled=true` 且字段非空；
   - `system_permission_schema.enabled=true` 且权限项非空。
3. 点击按钮进入组件参数配置页，页面展示：
   - 组件声明 Schema；
   - 当前组件已有配置列表；
   - 新增/编辑配置表单（配置名、启用状态、参数 JSON）。
4. 保存时执行 Schema 校验：
   - `required=true` 字段必须存在且非空；
   - 参数必须为 JSON 对象。

### 5.3 Django 数据模型
新增通用模型 `ComponentSystemParamConfig`：
1. `module_name`：模块名（如 communicate）。
2. `component_key`：组件唯一标识（如 communicate.dingtalk_component）。
3. `config_name`：配置名（同组件内唯一，如 test/prod）。
4. `display_name`：展示名。
5. `is_enabled`：配置启停。
6. `params`：JSON 参数值（字段名由 Schema 定义）。
7. `schema_snapshot`：保存时的 Schema 快照，便于追溯。
8. `description`、时间戳字段。

### 5.4 组件读取规则升级
1. 组件读取配置时优先读取 `ComponentSystemParamConfig(component_key, config_name)`。
2. 显式传参仍保持最高优先级。
3. 为兼容历史通信配置，可降级读取旧模型（provider + name）。
4. 读取后按组件必要字段校验，缺失立即返回明确错误。

### 5.5 组件参数分层规范（系统参数 + API 参数）
为满足“组件配置标准化 + demo 测试参数标准化”，组件参数统一分为两层：
1. **系统参数（System Params）**：组件级共享参数，典型为 `api_key`、`webhook_url`、`secret` 等敏感配置，来源于组件配置页（`system_param_schema`）。
2. **API 参数（API Params）**：单个 API 调用时的业务参数，典型为 `text`、`prompt`、`model`、`json_mode`、`timeout_seconds` 等，来源于测试页表单。

约束：
1. 每个组件必须声明组件配置能力，统一通过 `system_param_schema` 描述；若组件无系统参数，也需显式声明 `enabled=false` 与空字段列表，避免“是否可配置”语义不明确。
2. 每个 API 必须提供可用于测试页渲染的参数 Schema，统一采用与 `system_param_schema.fields` 同构的字段定义模式（字段名、必填、敏感、说明、默认值），并扩展 `value_type`（`string/int/float/bool/json`）用于运行时解析。
3. demo 代码中默认填写/示例的参数属于 API 参数，不得写入系统参数；系统参数优先走组件配置或显式传参。
4. 测试页提交 API 参数时，按 Schema 执行类型转换与必填校验，校验失败返回明确字段错误，不进入实际调用。

### 5.6 测试页面（Demo Runner）设计
在 component 功能页为每个 API 提供“测试 API”入口，进入统一测试页：
1. 页面展示：
   - 所属组件与 API 路径；
   - 系统参数提示（是否已配置、配置入口）；
   - API 参数 Schema 表格（配置项/配置值/说明），交互模式与组件配置页保持一致。
2. 测试执行流程：
   - 用户填写 API 参数；
   - 服务端按 `demo_param_schema` 做必填校验与类型转换；
   - 通过 `tools/component_call_tool.ComponentCallTool.control_call(function_path, kwargs)` 执行；
   - 页面展示结构化执行结果（成功/失败、返回 JSON）。
3. 安全与边界：
   - 敏感字段使用密码输入框；
   - `json` 类型字段必须是合法 JSON；
   - 可选参数留空时不传入目标函数；
   - 组件函数签名需兼容“可选参数省略调用”：凡在 `demo_param_schema` 中声明为非必填的参数，函数定义必须提供默认值，避免 `missing required positional argument`；
   - 对异常统一捕获并返回可读错误。

### 5.7 系统权限配置机制（System Permission）
组件可能依赖系统级权限（如 macOS 屏幕录制/辅助功能）或运行环境权限（如 Python 环境可写、pip 缓存目录可写）。系统权限采用“声明 + 校验 + 引导”策略，不在 Django 页面直接做系统提权：
1. 组件声明：
   - 在模块 `README.json -> components[]` 中新增 `system_permission_schema`。
   - 字段示例：
     - `enabled`：是否启用权限配置；
     - `permissions`：权限项清单（`key`、`name`、`required`、`description`、`grant_guide`、`grant_url`）。
2. 页面配置：
   - 组件配置页新增“系统权限配置”区块，展示权限清单与当前确认状态；
   - 用户在页面中对权限项执行“已授予/未授予”确认，保存到 Django 数据库。
3. 运行时校验：
   - 测试页执行 API 前，校验组件 `required=true` 的权限是否已确认；
   - 未确认时拒绝执行，返回缺失权限及配置入口；
   - 已确认后才允许进入组件调用。
4. 职责边界：
   - Django 页面仅提供权限声明、状态记录与操作指引；
   - OS 真正提权必须由用户在系统设置中完成。

### 5.9 迁移一致性与降级策略
为避免新功能上线后因数据库迁移未执行导致页面 500，需增加迁移一致性降级机制：
1. 当权限确认表不存在时（如 `collector_componentsystempermissiongrant` 未创建）：
   - 页面不抛 500；
   - 权限保存操作返回明确提示“请先执行 migrate”；
   - 读取权限状态降级为空状态，并在页面展示迁移提示。
2. 仅在权限存储可用时启用“必需权限拦截执行”；
3. 迁移执行后自动恢复完整校验链路，无需手工回滚配置。

### 5.10 管理员密码输入策略（仅运行时）
针对少量需要管理员权限的组件操作（如 pip 安装/卸载）：
1. 密码输入仅允许在测试页运行时临时输入；
2. 页面可弹窗输入一次密码并填入当前请求；
3. 密码不写入数据库、不写日志、不回显到结果区；
4. 组件执行完成后立即丢弃，不做会话持久化。

### 5.8 Python 依赖安装权限策略
针对 pip 运行权限与目录可写问题，组件调用层遵循以下策略：
1. 运行时自动安装依赖默认关闭（避免在 Django 服务进程中触发 root/pip 写权限风险）。
2. 缺少依赖时返回明确错误并提示使用虚拟环境预装依赖。
3. 若确需启用运行时安装，必须显式开启开关，并在受控环境中执行，不建议使用 `sudo` 直接运行 Django。

### 5.9 组件功能列表页状态与启停交互
为满足“在组件列表中直接查看状态并快速启停”的管理需求，组件功能列表页新增以下规则：
1. 状态展示：
   - 每个组件卡片展示当前状态，仅分为“已启用”和“已停用”；
   - 状态值来源于 `component.get_component_enabled(component_key)`；
   - 若组件索引存在但状态文件无记录，按 `component_index.json` 中 `default_enabled` 解析。
2. 启停按钮：
   - 在组件卡片右上角操作区（与“组件配置/下载组件”同区域）新增单个按钮；
   - 按钮文案根据当前状态动态切换：当前“已启用”时显示“停用”，当前“已停用”时显示“启用”；
   - 点击后执行 POST 切换组件状态并回到当前列表页（保留模块与检索条件）。
3. 系统权限信息展示：
   - 组件卡片中增加“系统权限信息”展示区；
   - 数据来源于组件声明的 `system_permission_schema.permissions` 与 Django 权限确认记录；
   - 每项权限展示：权限名/权限 key、是否必需、当前确认状态（已确认/未确认）、说明与授权指引链接；
   - 组件未声明系统权限时展示“无系统权限要求”。
4. 交互边界：
   - “展开 API/收起 API”交互不变；
   - 点击启停按钮不触发卡片折叠；
   - 启停失败时给出明确错误提示，不更新前端假状态。

### 5.10 Django 侧边栏工具组件与工具集二级菜单
为满足“在 Django 平台中统一查看组件能力与工具集能力”的导航需求，侧边栏与页面新增以下规则：
1. 菜单命名调整：
   - 原“组件”一级菜单改名为“工具组件”；
   - 保持原有组件模块子菜单（`communicate/observe/decide/handle`）不变，避免影响既有入口与使用习惯。
2. 二级菜单新增：
   - 在“工具组件”下新增“工具集”二级菜单项；
   - “工具集”必须位于该二级菜单第一项，组件模块菜单项顺序保持原有定义顺序。
3. 工具集列表页能力：
   - 新增独立页面用于展示工具集列表与基础信息；
   - 信息维度至少包含：工具集名称、目录路径、README 摘要、关键模块文件；
   - 页面交互风格参照组件功能页，支持关键字检索和基础统计信息展示。
4. 数据来源与边界：
   - 工具集信息来源于 `tools` 目录结构与各工具 `README.md`；
   - 仅做“读取与展示”，不引入工具启停写操作，不改变现有 `ComponentCallTool` 调用链路。

### 5.11 Django 启动导入路径兼容
为保证 Django 在不同启动方式下可稳定导入仓库级包（如 `tools`、`component`），增加以下约束：
1. 启动入口 `core/manage.py` 必须将仓库根目录加入 `sys.path`。
2. 部署入口 `core/reqcollector/wsgi.py` 与 `core/reqcollector/asgi.py` 需执行同样路径注入，避免仅开发环境可用。
3. 业务代码中统一使用 `from tools...`、`from component...` 的绝对导入，不在各业务模块重复注入路径逻辑。
4. 导入路径策略属于基础运行时能力，变更时需优先保证兼容 `runserver`、`migrate`、`shell` 与 WSGI/ASGI 部署场景。

### 5.12 组件与工具操作系统字段与查询机制
为满足“组件/工具按操作系统展示与筛选”的能力，新增以下规则：
1. 元数据字段：
   - 组件：在 `component/component_index.json` 与各模块 `component/<module>/README.json -> components[]` 中新增 `supported_systems` 字段；
   - 工具：在 `tools/<tool>/README.md` 中新增“支持操作系统”声明（文本字段，值包含 `macos/linux/windows`）。
2. 字段语义：
   - `supported_systems` 为数组，允许值：`macos`、`linux`、`windows`；
   - 若组件确实仅支持某系统（如 `handle.macos_terminal_component`），按单系统声明，不做跨平台兜底改造；
   - 若能力可跨平台，优先声明三系统支持。
3. Django 查询页行为：
   - 组件功能页与工具集页新增“操作系统”筛选项（`all/macos/linux/windows`）；
   - 默认筛选值为“当前运行 Django 进程的操作系统”；
   - 支持用户手动切换为其他系统或“全部”。
4. 运行时识别规则：
   - 基于 Python `platform.system()` 归一化映射：
     - `Darwin -> macos`
     - `Linux -> linux`
     - `Windows -> windows`
   - 未识别系统默认回退到 `linux`（仅用于页面默认值，不改变组件实际运行约束）。
5. 向后兼容：
   - 历史组件或工具缺失 OS 字段时，页面层按“全平台可见”降级处理，避免因元数据缺失导致能力不可见。

### 5.13 Django 侧边栏智能体菜单下挂技能/规则查询管理
为满足“在 Django 平台统一查看并检索 `.cursor/skills` 与 `.cursor/rules`，并聚合到智能体导航下”的管理需求，新增以下规则：
1. 一级菜单调整：
   - 移除独立一级菜单 `系统`；
   - 将原 `系统` 下的 `技能（skills）`、`规则（rules）` 迁移到一级菜单 `智能体（agents）` 下；
   - 侧边栏保持 `聊天`、`智能体（agents）`、`工具组件`、`设置` 的一级结构。
2. 二级菜单归并：
   - 在 `智能体（agents）` 下保留并扩展二级菜单项：`心法（mindforge）`、`号令（helm）`、`技能（skills）`、`规则（rules）`；
   - 点击各二级菜单进入对应查询管理页。
3. 技能列表页能力：
   - 数据来源为仓库目录 `.cursor/skills`；
   - 列表展示至少包含：技能名、目录路径、`SKILL.md` 是否存在、摘要信息、关键文件清单；
   - 摘要优先读取 `SKILL.md` 中的 `description` 字段，缺失时再使用文本首段降级；
   - 支持关键字检索（名称、路径、摘要文本匹配）。
4. 规则列表页能力：
   - 数据来源为仓库目录 `.cursor/rules`；
   - 列表展示至少包含：规则文件名、文件路径、摘要信息、更新时间；
   - 摘要优先读取规则文档中的 `description` 字段，缺失时再使用文本首段降级；
   - 支持关键字检索（文件名、路径、摘要文本匹配）；
   - 支持点击规则项进入详情页，展示 `.md` 文档全文。
5. 边界与约束：
   - 默认以“查询与展示”为主；规则编辑与技能导入/导出能力在专用入口中提供；
   - 当目录不存在或无可展示项时，页面需友好提示，不返回 500；
   - 页面布局与交互风格参照现有“工具集列表”页面，保持一致性。

### 5.14 Django 规则文档详情与在线编辑
为满足“规则支持点击进入并在线编辑”的需求，新增以下规则：
1. 入口与跳转：
   - 在规则列表页中，每条规则项提供“查看/编辑”入口；
   - 点击后进入规则详情页，定位到对应规则文件。
2. 详情页展示能力：
   - 展示规则文件相对路径、更新时间、文本内容；
   - 仅针对 `.md` 文本文件开放在线编辑区域。
3. 保存能力：
   - 支持在详情页直接编辑并保存文件内容；
   - 保存成功后停留在当前详情页并提示成功信息。
4. 安全与边界：
   - 必须执行路径安全校验，禁止目录穿越（只允许访问 `.cursor/rules` 目录范围内文件）；
   - 非 `.md` 或不可编辑文件返回明确提示，不执行写入；
   - 文件不存在、读写失败等异常场景需友好提示，不返回 500。

### 5.15 Django 技能单项导入/导出（zip）
为满足“技能支持单个技能导出与导入（压缩包）”的需求，新增以下规则：
1. 导出能力：
   - 技能列表中每个技能卡片右上角提供“导出技能”按钮（交互风格参考组件页面）；
   - 点击后将该技能目录打包为单个 zip 并下载。
2. 导入能力：
   - 技能列表页提供“导入技能”入口，支持上传 zip；
   - 上传后按单技能目录解压到 `.cursor/skills/<skill_name>` 对应目录下。
3. 压缩包约束：
   - zip 需只包含一个顶层技能目录；
   - 顶层目录名作为技能目录名。
4. 安全与边界：
   - 上传解压必须执行路径安全校验，禁止 zip slip（目录穿越）；
   - 文件类型仅允许 `.zip`；
   - 导出/导入失败需返回可读错误，不返回 500。

### 5.16 工具集新增 macOS 终端对象工具（基于 ComponentCallTool）
为满足“在工具集层获得可复用终端对象并支持输入输出互操作”的需求，新增以下规则：
1. 工具目录与定位：
   - 在 `tools` 下新增独立工具目录 `tools/macos_terminal_tool`；
   - 该工具负责“对象化会话管理与调用编排”，不重复实现 shell 子进程逻辑。
2. 调用链路约束：
   - 工具调用 `component.handle.create_macos_terminal_session`、`component.handle.run_macos_terminal_command`、`component.handle.get_macos_terminal_output`、`component.handle.close_macos_terminal_session` 时，必须统一通过 `tools/component_call_tool.ComponentCallTool.control_call`；
   - 禁止在工具内直接导入 `component` 代码。
3. 终端对象模型：
   - 工具层提供“终端对象”抽象，至少包含：对象 ID、`session_id`、当前输出偏移量、创建参数（`cwd`、`shell_mode`）；
   - 同一对象可多次输入命令并复用会话上下文，支持 `cd` 后继续执行后续命令。
4. 输入输出互操作能力：
   - 支持输入命令并同步返回本次执行输出（含退出码）；
   - 支持按 offset 增量读取累计输出，便于轮询或流式消费；
   - 支持对象级关闭，关闭后释放会话并禁止继续输入/读取。
5. 返回与异常约束：
   - 工具对外返回统一结构：成功 `success + data`，失败 `success + error`；
   - 组件调用失败、会话不存在、对象不存在、平台不支持等场景需返回明确可读错误；
   - 对象关闭失败需保留原始错误信息，避免静默吞错。
6. 平台边界：
   - 工具层不绕过组件的平台校验；在非 macOS 环境调用时，按组件返回错误透传；
   - 工具 `README.md` 必须显式声明支持系统为 `macos`。

### 5.17 Django 侧边栏智能体菜单与智能体项管理（zip 导入/导出）
为满足“在 Django 平台中管理 `agents` 目录，并支持按模块检索与单项导入/导出”的需求，新增以下规则：
1. 一级菜单新增：
   - 在侧边栏 `工具组件` 上方新增一级菜单 `智能体（agents）`；
   - 保持与现有一级菜单一致的展开/收缩与激活高亮交互。
2. 二级菜单新增：
   - 在 `智能体（agents）` 下新增二级菜单项 `心法`、`号令`；
   - `心法` 对应目录固定为 `agents/mindforge`；
   - `号令` 对应目录固定为 `agents/helm`，用于承载循环与状态机逻辑相关的 agent 组件；
   - 菜单顺序要求：`心法` 第一项，`号令` 第二项；后续模块可按同结构扩展。
3. 智能体项检索页能力：
   - 新增独立查询管理页，按目录项展示对应模块目录（如 `agents/mindforge`、`agents/helm`）下智能体项；
   - 智能体项以“目录”为最小管理单元（每项至少包含一个目录）；
   - 列表展示至少包含：项名称、目录路径、`README.md` 是否存在、摘要信息、关键文件清单、更新时间；
   - 支持关键字检索（名称、路径、摘要文本匹配）。
4. 单项导出能力：
   - 每个智能体项提供“导出”按钮；
   - 点击后将该项目录打包为单个 zip 并下载；
   - zip 顶层目录名与项目录名一致。
5. 单项导入能力：
   - 智能体项列表页提供“导入”入口，支持上传 zip；
   - zip 仅允许包含一个顶层目录，目录名作为新智能体项名；
   - 解压目标目录为 `agents/<module_name>/<item_name>`；
   - 当目标目录已存在时拒绝覆盖并返回明确错误，避免误覆盖。
6. 安全与边界：
   - 上传文件类型仅允许 `.zip`；
   - 导入时必须执行 zip slip 安全校验（目录穿越拦截）；
   - 路径解析必须限制在目标模块目录范围内（如 `agents/mindforge`、`agents/helm`）；
   - 目录不存在、压缩包不合法、解压失败等场景返回可读错误，不返回 500。

## 6. 组件注册与兼容映射
### 6.1 注册索引文件
新增 `component/component_index.json`，作为组件层元数据源，包含：
1. `components`：组件定义（组件 key、模块、目录、导出函数、默认启用状态）。
2. `function_to_component`：函数路径与组件 key 映射。
3. 不维护旧路径别名字段，避免隐式兼容导致规则不清。

### 6.2 解析流程
`call_by_path(function_path, kwargs)` 执行前：
1. 按 `function_to_component` 判断函数是否由组件托管；
2. 组件托管函数先校验组件启停状态；
3. 通过 import 机制解析并调用函数；
4. 不通过模块级转发层进行路径兼容。

## 7. 组件启停机制
### 7.1 状态存储
新增 `component/component_state.json`：
1. 存储结构：`{ "component_key": true/false }`。
2. 若某组件无显式状态，使用 `component_index.json` 的 `default_enabled`。

### 7.2 管理 API
在 `component` 顶层新增组件管理函数：
1. `component.list_components()`：返回组件清单和当前状态。
2. `component.set_component_enabled(component_key, enabled)`：设置组件启停并持久化。
3. `component.get_component_enabled(component_key)`：查询单组件是否启用。

### 7.3 调用约束
1. 停用组件被调用时抛出明确错误（包含组件标识）。
2. 组件不存在或映射缺失时，不阻塞无映射函数的正常解析（兼容未纳管函数）。

## 8. 升级兼容策略
1. 不保留隐式兼容转发层，调用方仅使用文档登记的规范函数路径。
2. 如需路径迁移，必须在设计文档与 `README.json` 显式发布并约定切换窗口。
3. 组件启停约束始终基于规范函数路径生效。
4. 兼容策略以“显式发布 + 明确切换”替代“代码隐式兜底”。

## 9. 数据与文档同步策略
1. 新增或升级组件时，必须同步更新：
   - `component/component_index.json`
   - `component/README.json`
   - 对应模块 `README.json`
   - 组件目录内 `requirements.txt` 与 `README.md`
2. 组件启停状态写入 `component/component_state.json`，由运行时维护。

## 10. 风险与回滚
1. 风险：组件映射配置错误导致路径解析失败。
2. 控制：对索引读取异常做兜底，不影响原始无映射调用。
3. 回滚：优先恢复组件状态；必要时恢复上一版本索引与导出配置。

## 11. 测试策略
1. 验证现有函数路径可继续调用（兼容性）。
2. 验证组件停用后调用被拒绝，启用后恢复。
3. 验证旧路径别名可正确路由到目标函数。
4. 验证 `list_components`、`set_component_enabled`、`get_component_enabled` 行为正确。
5. 验证 `component.handle.file_reader_component` 的文件读取、行区间读取、关键字/正则检索结果与迁移前行为一致。
6. 验证 `component.call_by_path("component.handle.*")` 可正确命中组件映射并执行启停校验。
7. 验证 `component.call_by_path("component.communicate.*")` 可正确命中通信组件映射。
8. 验证三方通信组件在“显式传参”路径下可正确拼装请求。
9. 验证三方通信组件在“仅传 `config_name`”时可从 Django 数据库正确读取参数。
10. 验证 `provider + name` 配置缺失、禁用、参数缺失时返回明确错误。
11. 验证带有 `system_param_schema` 或 `system_permission_schema` 的组件在功能页展示“组件配置”按钮。
12. 验证组件参数配置页可新增/编辑多套配置，并按 Schema 校验必填字段。
13. 验证组件运行时可按 `component_key + config_name` 读取通用参数配置。
14. 验证每个组件均声明组件配置 Schema（含无系统参数组件的显式禁用声明）。
15. 验证 API 测试页可按 `demo_param_schema` 自动渲染参数输入表格。
16. 验证 API 测试页对 `int/float/bool/json` 参数可正确转换与校验。
17. 验证 API 测试页在可选参数留空时不会向目标函数传参。
18. 验证 API 测试页通过 `ComponentCallTool.control_call` 调用后可正确展示成功与异常结果。
19. 验证组件 API 在省略可选参数（如 `api_key`）时仍可正常执行默认读取逻辑（如读取组件系统配置）。
20. 验证组件配置页可展示并保存 `system_permission_schema` 权限确认状态。
21. 验证测试页在必需权限未确认时拒绝执行并给出可读提示。
22. 验证组件调用工具在默认策略下不会触发运行时自动 pip 安装。
23. 验证权限确认表缺失时页面不会报 500，且返回明确 migrate 指引。
24. 验证管理员密码仅在单次测试调用内使用，不落库且不回显。
23. 验证组件列表页可正确展示“已启用/已停用”状态。
24. 验证组件列表页启停按钮文案随状态切换（已启用->停用，已停用->启用）。
25. 验证点击启停按钮后组件状态持久化到 `component_state.json` 并在列表刷新后生效。
26. 验证组件列表页可展示系统权限信息（权限名、必需性、确认状态、授权链接）。
27. 验证点击启停按钮不会触发组件卡片“展开 API/收起 API”折叠行为。
28. 验证组件 `supported_systems` 字段可被组件功能页正确读取与展示。
29. 验证组件功能页“操作系统”筛选默认值等于当前运行系统，且可切换 `all/macos/linux/windows`。
30. 验证工具集页可读取工具 README 的“支持操作系统”字段并按系统筛选。
31. 验证仅系统专属组件（如 macOS 终端）在非匹配系统筛选下被正确隐藏。

## 12. control/agents ReAct 引擎设计
### 12.1 目标与边界
1. 在 `control/agents` 下提供可复用的 ReAct（Reason + Act）执行引擎。
2. 引擎仅作为“控制层编排器”，不重复实现已有组件能力，工具调用统一复用 `tools/component_call_tool`。
3. 大模型调用统一复用 `component.decide.chat_completion`（通过 `ComponentCallTool.control_call` 间接调用），不新增并行的大模型 SDK 封装。
4. 优先保证“无额外依赖可运行”；如环境存在 `langgraph`，可选启用图模式执行。

### 12.2 目录与模块设计
在 `control/agents` 新增以下文件：
1. `control/__init__.py`：控制层顶层包声明。
2. `control/agents/__init__.py`：导出 ReAct 引擎公共 API。
3. `control/agents/react_engine.py`：ReAct 核心实现（循环执行 + 工具路由 + 结果归档）。
4. `control/agents/README.md`：引擎用途、输入输出、集成示例。

### 12.3 核心数据结构
1. `ReActTool`：
   - `name`：工具名（给模型看的短名称）。
   - `function_path`：组件函数路径（如 `component.handle.read_file`）。
   - `description`：工具用途说明。
2. `ReActEngineConfig`：
   - `model`：大模型标识（默认 `qwen-plus`）。
   - `config_name`：组件系统参数配置名（默认 `default`）。
   - `api_key`：可选显式 API Key（显式传参优先）。
   - `max_steps`：最大 ReAct 步数，避免无限循环。
   - `temperature`、`max_tokens`：模型采样参数。
   - `use_langgraph_if_available`：是否在检测到 `langgraph` 时启用图执行。
3. `ReActStepRecord`：
   - `step`、`thought`、`action`、`observation`、`raw_model_output`、`error`。
4. `ReActRunResult`：
   - `success`、`final_answer`、`steps`、`error`。

### 12.4 推理-执行协议（模型输出协议）
为降低解析歧义，ReAct 轮次采用 JSON 协议（字符串响应中包含 JSON）：
1. 继续执行动作：
   - `{"thought":"...","action":{"tool":"<tool_name>","kwargs":{...}}}`
2. 结束并输出结论：
   - `{"thought":"...","final_answer":"..."}`
3. 协议校验失败时，按失败观测回填到上下文，进入下一轮重试，直到达到 `max_steps`。

### 12.5 执行流程
1. 初始化工具索引（`tool_name -> ReActTool`）。
2. 构造系统提示词：包含任务目标、工具清单、输出 JSON 协议、约束（一次只调用一个工具）。
3. 每轮通过 `ComponentCallTool.control_call("component.decide.chat_completion", kwargs)` 获取模型响应。
4. 解析 JSON：
   - 有 `final_answer`：结束；
   - 有 `action`：校验工具名并通过 `ComponentCallTool.control_call(tool.function_path, kwargs)` 执行工具；
   - 执行结果写入 `observation` 并继续下一轮。
5. 超过 `max_steps` 仍未结束，返回失败并提示“达到最大执行步数”。

### 12.6 LangGraph 可选策略
1. 当 `use_langgraph_if_available=true` 且环境可导入 `langgraph`，使用最小状态图：
   - `reason` 节点：调用 LLM 产生 action/final。
   - `act` 节点：执行工具并回写 observation。
   - 条件边：`final -> END`，`action -> act -> reason`。
2. 未安装 `langgraph` 或图执行异常时，自动降级到内置循环执行，不影响主流程可用性。

### 12.7 异常与安全
1. 工具白名单：仅允许调用初始化时注册的工具名，禁止模型直接提交任意 `function_path`。
2. 工具执行异常不直接中断主流程，而是记录到 observation，允许模型下一轮自修复。
3. 统一保留 `raw_model_output`，便于问题追踪。
4. 不在日志和结果中主动展开敏感字段值（如 api_key）。

### 12.8 测试策略补充（ReAct）
1. 验证引擎可完成“模型->工具->模型->最终答案”的最小闭环。
2. 验证模型返回非法 JSON 时，引擎可记录错误并继续下一轮。
3. 验证未知工具名会被拒绝并反馈 observation。
4. 验证 `max_steps` 达到上限后返回失败。
5. 验证有无 `langgraph` 两种环境均可运行（图执行与降级循环执行）。
6. 单元测试目录按镜像规则落位：`control/agents/react_engine.py` 对应 `test/test_control/test_agents/test_react_engine.py`，目录名采用 `test_` + 被测目录名，测试文件采用 `test_*.py` 命名。
7. 为兼容 `python -m unittest test.test_xxx...` 模块路径执行方式，`test` 及其镜像子目录需包含 `__init__.py`，避免与 Python 标准库 `test` 包解析冲突。

### 12.9 mindforge ReAct 引擎结构化解耦
为降低单文件复杂度并提升可维护性，`agents/mindforge` 下 ReAct 引擎按“目录化 + 模块职责分离”改造：
1. 目录结构：
   - `agents/mindforge/react_engine/` 作为独立引擎目录；
   - 目录内至少包含：`__init__.py`、`engine.py`、`models.py`、`protocol.py`、`executor.py`、`README.md`。
2. 职责拆分：
   - `models.py`：数据结构定义（`ReActTool`、`ReActEngineConfig`、`ReActStepRecord`、`ReActRunResult`）；
   - `protocol.py`：模型输出 JSON 协议解析与文本提取；
   - `executor.py`：工具执行与白名单校验；
   - `engine.py`：主循环编排、LangGraph 可选执行、消息构造；
   - `__init__.py`：统一导出公共 API。
3. 兼容约束：
   - 继续支持 `from agents.mindforge.react_engine import ReActEngine` 的导入方式；
   - 不改变已有 ReAct 输入输出协议与返回结构；
   - 工具调用与模型调用链路保持不变，仍通过 `ComponentCallTool`。
4. 文档约束：
   - `agents/mindforge/react_engine/README.md` 明确目录职责、输入输出协议与快速使用示例；
   - `agents/mindforge/README.md` 保留模块级说明，并指向 `react_engine` 子目录。

### 12.10 helm 号令：原始需求收集流程机制抽取
为满足“将聊天中的原始需求收集流程与状态机制沉淀为可复用号令组件”的需求，新增以下规则：
1. 目录与命名：
   - 在 `agents/helm` 下新增独立号令目录 `agents/helm/requirement_session_command/`；
   - 目录内至少包含：`__init__.py`、流程实现文件、`README.md`。
2. 抽取范围：
   - 抽取会话阶段流转机制：`collecting -> organizing -> completed`；
   - 抽取“用户确认触发词”判定逻辑（进入整理与确认完成两类）；
   - 抽取流程决策接口，供 Django 聊天流程调用，避免在 `views.py` 内散落硬编码。
3. 对外接口：
   - 号令组件对外提供稳定 API（例如确认判定、阶段流转决策）；
   - 业务层仅依赖该 API，不直接依赖内部关键词集合实现细节。
4. 集成约束：
   - `core/collector/views.py` 的原始需求会话处理需改为通过该号令组件驱动；
   - 保持现有用户体验与文案不变，避免行为回归。
5. 文档约束：
   - `agents/helm/requirement_session_command/README.md` 需描述流程状态机、关键词策略、调用示例；
   - 说明该号令可被其他模块复用（如后续多入口需求采集流程）。
