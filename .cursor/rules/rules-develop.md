---
description: "后端数据库开发规范：ORM定义结构，原生SQL执行操作"
alwaysApply: false
globs: "**/*.py,**/*.ts,**/*.java" # 根据实际后端语言调整
---

# 后端数据库开发规范

## 核心原则
1. **表结构定义**：必须使用 ORM (如 SQLAlchemy, TypeORM, Hibernate 等) 来定义数据库表格结构和关系。
2. **数据操作**：在进行增删改查 (CRUD) 操作时，**严禁**使用 ORM 自带的查询方法，必须编写并执行原生的 SQL 语句。

## 示例
- ✅ 正确：使用 ORM 定义 Model，但在 Service 层使用 `db.execute("SELECT * FROM ...")`。
- ❌ 错误：使用 `Model.objects.filter()` 或 `repository.find()` 等 ORM 查询方法。