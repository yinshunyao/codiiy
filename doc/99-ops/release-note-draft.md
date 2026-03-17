# 发布文档草稿（持续累积）

> 说明：
> - 本文档用于记录日常细小发布项（新增功能/变更功能/解决问题）。
> - 不要求立即同步到正式发布文档 `release-note.md`。
> - 收到“发布整理/发布汇总”指令后，再从本草稿提炼并精简到正式发布文档。

## 使用规则
1. 每次记录使用一条独立条目，尽量简短、可追溯。
2. 条目至少包含：日期、类型、摘要、关联改动（可为文档/模块/文件）。
3. 正式发布后，可给已纳入版本的条目增加“已收录”标记，避免重复汇总。

## 草稿条目（最新在前）

### 2026-03-17
- [新增功能] 新增 `cursor_local` 适配器，支持 Cursor CLI `stream-json` 解析、`--resume` 续跑失败自动重试、指令文件注入与环境 hello probe。
  - 关联：`adapter/cursor_local/`、`adapter/registry.py`、`test/test_adapter/test_cursor_local_adapter.py`、`doc/01-or/【适配器】Cursor Local 适配器实现.md`
- [变更功能] 修复菜单命名联动细节：系统品牌名随方案切换（开智枢/codiiy平台）；“侠谱”迁移到“武库”分组首位，并移除侧栏创建按钮。
  - 关联：`core/templates/collector/partials/sidebar_menu.html`、`core/collector/views.py`、`core/settings/menu_naming_schemes.json`
- [文档更新] 新增菜单问题追溯 QA 文档，补充品牌联动与菜单层级回归测试点。
  - 关联：`doc/91-qa/【菜单功能】系统名称与侠谱菜单位置问题.md`、`doc/03-tr/01 会话原始需求收集系统测试需求.md`
- [变更功能] 菜单支持“标准中文/武侠风”命名方案切换，默认武侠风；个人设置新增方案切换入口，侧栏一级/二级菜单与组件子模块文案联动更新。
  - 关联：`core/settings/menu_naming_schemes.json`、`core/collector/views.py`、`core/templates/collector/partials/sidebar_menu.html`、`core/templates/collector/profile_settings.html`、`test/test_core/test_collector/test_views.py`
- [文档更新] 补充菜单命名改造的开发设计、测试设计与 OR 工作项归档。
  - 关联：`doc/02-dr/01 会话原始需求收集系统设计.md`、`doc/03-tr/01 会话原始需求收集系统测试需求.md`、`doc/01-or/【菜单功能】武侠名称对照.md`
- [新增功能] 移植 paperclip adapter 对接能力，新增 `adapter/` 模块（Python 实现），支持 process（命令行）和 http（HTTP 接口）两种 adapter 类型。
  - 关联：`adapter/`、`doc/01-or/【adapter】对接比较成熟的agent程序.md`、`doc/02-dr/11 adapter/11.01 adapter对接设计.md`
- [新增功能] 伙伴（CompanionProfile）新增 adapter_type 和 adapter_config 字段，创建/编辑伙伴时可点选 adapter 类型。
  - 关联：`core/collector/models.py`、`core/collector/forms.py`、`core/templates/collector/companion_form.html`、`core/collector/migrations/0027_companionprofile_adapter_fields.py`
- [变更功能] 会话消息卡片中的“回退/删除”（启用总结时含“摘”）按钮统一为同一行展示，提升操作区视觉一致性。
  - 关联：`core/templates/collector/session_list.html`、`test/test_core/test_collector/test_views.py`
- [文档更新] 同步补充消息操作按钮同行展示的需求、设计与测试条目。
  - 关联：`doc/01-or/01 整体结构设计.md`、`doc/02-dr/01 会话原始需求收集系统设计.md`、`doc/03-tr/01 会话原始需求收集系统测试需求.md`
- [变更功能] 聊天主窗口与伙伴会话窗口新增“单条消息删除”能力，支持按条删除用户消息或助手消息。 
  - 关联：`core/collector/views.py`、`core/collector/urls.py`、`core/templates/collector/session_list.html`、`test/test_core/test_collector/test_views.py`
- [文档更新] 同步补充会话消息删除的需求、设计与测试文档。 
  - 关联：`doc/01-or/01 整体结构设计.md`、`doc/02-dr/01 会话原始需求收集系统设计.md`、`doc/03-tr/01 会话原始需求收集系统测试需求.md`

### 2026-03-16
- [变更功能] Django 启动支持通过 `--project-dir` 显式设置项目目录；未提供时默认回退到 `core` 上一级目录。`[已收录 v0.1.3]`
  - 关联：`core/manage.py`、`core/reqcollector/path_bootstrap.py`、`core/reqcollector/asgi.py`、`core/reqcollector/wsgi.py`、`core/reqcollector/settings.py`
- [变更功能] 统一系统根目录语义：`doc/...` 路径默认按系统根目录解析，避免与 `core/doc/...` 混淆。`[已收录 v0.1.3]`
  - 关联：`core/collector/models.py`、`doc/02-dr/01 会话原始需求收集系统设计.md`
- [变更功能] 运维运行文档增加项目目录参数与环境变量说明。`[已收录 v0.1.3]`
  - 关联：`doc/99-ops/run.md`
