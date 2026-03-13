---
description: "后端数据库开发规范：ORM定义结构，原生SQL执行操作"
alwaysApply: false
globs: "**/*.py,**/*.ts,**/*.java,**/*.md" # 包含代码与设计文档约束
---

# 后端数据库开发规范

## 核心原则
1. **表结构定义**：必须使用 ORM (如 SQLAlchemy, TypeORM, Hibernate 等) 来定义数据库表格结构和关系。
2. **数据操作**：在进行增删改查 (CRUD) 操作时，**严禁**使用 ORM 自带的查询方法，必须编写并执行原生的 SQL 语句。

## 示例
- ✅ 正确：使用 ORM 定义 Model，但在 Service 层使用 `db.execute("SELECT * FROM ...")`。
- ❌ 错误：使用 `Model.objects.filter()` 或 `repository.find()` 等 ORM 查询方法。

## 组件查询/调用规范（强制）
1. 所有非组件模块（如 `tools`、`control`、`core` 等）在查询组件信息或调用组件函数时，必须通过 `tools/component_call_tool`。
2. 严禁在非组件模块中直接导入或直接调用 `component` 代码（包括 `component.call_by_path` 等）。
3. 若现有 `tools/component_call_tool` 无法满足需求，应先扩展该工具，再由业务模块接入；禁止在业务模块绕过工具直连组件。

## 组件调用示例
- ✅ 正确：`tool = ComponentCallTool(); tool.control_call(function_path=..., kwargs=...)`
- ❌ 错误：`from component import call_by_path` 后在 `tools/control/core` 中直接调用