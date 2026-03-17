---
description: "开发编码规范：设计先行、数据库ORM+原生SQL、组件调用规范"
alwaysApply: true
globs: "**/*.py,**/*.ts,**/*.tsx,**/*.java,**/*.md"
---

# 开发编码规范

## 设计先行原则（强制）

1. **编码前检查设计文档**：开始编写或修改功能代码之前，**必须**先确认 `doc/02-dr/` 中存在覆盖本次变更的设计文档。若不存在或未覆盖，需先补充设计文档。
2. **设计文档优先于代码**：当发现问题时，先检查设计文档是否存在问题，先修改设计文档，再修改代码实现。
3. **变更顺序**：需求变更 → 更新 OR 文档(01-or) → 更新设计文档(02-dr) → 更新测试设计(03-tr) → 修改代码 → 修改测试代码。严禁反向操作。

## 路径基准规范（强制）

1. **系统根目录固定**：Django 运行时的系统根目录固定为 `core` 的上一级目录（仓库根目录）。
2. **相对路径解析基准固定**：所有业务相对路径（如 `doc/...`、`tools/...`）必须相对于系统根目录解析，禁止依赖当前进程工作目录（`cwd`）。
3. **目录歧义禁止**：当用户或模型输入 `doc/...` 时，统一解释为 `<系统根目录>/doc/...`，不得解析为 `core/doc/...`。
4. **启动一致性**：`manage.py`、`wsgi.py`、`asgi.py` 必须保持一致的根目录初始化行为，避免不同启动方式出现路径分叉。
5. **启动可配置**：Django 启动前允许显式设置项目目录（推荐参数或环境变量）；若未提供，默认使用 `core` 的上一级目录。
6. **部署文档同步**：当启动参数、环境变量、部署命令或运行目录约束发生变更时，必须同步更新 `doc/99-ops/`（至少更新 `run.md`）。
7. **发布文档策略**：发布主文档 `doc/99-ops/release-note.md` 不要求每次实时更新；细小新功能/变更/问题修复先记录到 `doc/99-ops/release-note-draft.md`，待发布指令后再统一精简汇总。

## 后端数据库规范

### 核心原则
1. **表结构定义**：必须使用 ORM (如 SQLAlchemy, TypeORM, Hibernate 等) 来定义数据库表格结构和关系。
2. **数据操作**：在进行增删改查 (CRUD) 操作时，**严禁**使用 ORM 自带的查询方法，必须编写并执行原生的 SQL 语句。

### 示例
- ✅ 正确：使用 ORM 定义 Model，但在 Service 层使用 `db.execute("SELECT * FROM ...")`。
- ❌ 错误：使用 `Model.objects.filter()` 或 `repository.find()` 等 ORM 查询方法。

## 组件查询/调用规范（强制）
1. 所有非组件模块（如 `tools`、`control`、`core` 等）在查询组件信息或调用组件函数时，必须通过 `tools/component_call_tool`。
2. 严禁在非组件模块中直接导入或直接调用 `component` 代码（包括 `component.call_by_path` 等）。
3. 若现有 `tools/component_call_tool` 无法满足需求，应先扩展该工具，再由业务模块接入；禁止在业务模块绕过工具直连组件。

### 示例
- ✅ 正确：`tool = ComponentCallTool(); tool.control_call(function_path=..., kwargs=...)`
- ❌ 错误：`from component import call_by_path` 后在 `tools/control/core` 中直接调用