---
description: "测试目录结构规范：单元测试镜像映射 + E2E Playwright 测试组织"
globs:
  - "**/test/**/*.py"
  - "**/test/**/*.ts"
  - "**/test/**/AGENTS.md"
alwaysApply: true
---

# 测试目录结构规范

当处理 `test` 目录下的测试代码时，必须遵循以下约束。

## 一、单元/集成测试 — 目录映射规则（强制）

- 测试目录应尽量与被测试代码目录结构一致，按层级镜像组织。
- 测试代码目录名称由 `test_` + 被测试目录名称组成。
- 对任意被测试目录路径 `a/b/c`，其对应测试目录路径应为 `test/test_a/test_b/test_c`。

示例：
- 被测目录：`component/observe/screen_capture_component`
- 测试目录：`test/test_component/test_observe/test_screen_capture_component`

### 文件命名与放置

- 测试文件命名使用 `test_*.py`。
- 测试文件应放在其对应的镜像测试目录下，避免跨目录混放。

### 变更要求

- 新增被测目录时，应同步新增对应测试目录，保持结构可追踪。
- 若调整被测目录结构，应先调整测试目录映射，再修改具体测试实现。

## 二、E2E 系统级测试 — Playwright 约定（强制）

WEB 相关功能的端到端测试统一使用 **Playwright** 框架，代码放在 `test/e2e/` 目录下。

### 目录组织

- `test/e2e/` 下按**功能模块**建立子目录，模块名与 `doc/02-dr/` 中的设计模块对应。
- 每个模块目录下放置该模块的 E2E 测试文件。

```
test/e2e/
├── task-create/          # 对应 02-dr/01 任务创建
│   ├── basic-info.spec.ts
│   └── annotation-config.spec.ts
├── data-source/          # 对应 02-dr/02 数据资产
│   └── source-create.spec.ts
├── annotation/           # 对应 02-dr/03 标注
│   └── annotation-flow.spec.ts
├── pre-annotate/         # 对应 02-dr/06 预标注
│   └── pre-annotate-flow.spec.ts
└── fixtures/             # 共享测试数据和工具函数
    └── auth.ts
```

### 文件命名

- 测试文件命名使用 `*.spec.ts`（Playwright TypeScript 规范）。
- 文件名应反映被测试的用户流程或页面，使用 kebab-case（如 `task-create-wizard.spec.ts`）。

### 内容要求

- 每个测试文件聚焦一个**用户流程**或**页面场景**。
- 测试应覆盖核心用户路径（Happy Path），关键异常路径按需补充。
- 共享的登录、数据准备等逻辑抽取到 `fixtures/` 目录。

### 变更要求

- 新增 WEB 页面功能时，**必须**同步在 `test/e2e/` 中新增对应 E2E 测试。
- 修改现有页面交互逻辑时，检查并更新对应的 E2E 测试用例。
