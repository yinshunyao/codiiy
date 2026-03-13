---
description: "测试目录结构规范：与被测代码目录保持镜像，目录名使用 test_ 前缀"
globs:
  - "**/test/**/*.py"
  - "**/test/**/AGENTS.md"
alwaysApply: false
---

# 测试目录结构规范

当处理 `test` 目录下的测试代码时，必须遵循以下约束。

## 目录映射规则（强制）

- 测试目录应尽量与被测试代码目录结构一致，按层级镜像组织。
- 测试代码目录名称由 `test_` + 被测试目录名称组成。
- 对任意被测试目录路径 `a/b/c`，其对应测试目录路径应为 `test/test_a/test_b/test_c`。

示例：
- 被测目录：`component/observe/screen_capture_component`
- 测试目录：`test/test_component/test_observe/test_screen_capture_component`

## 文件命名与放置

- 测试文件命名使用 `test_*.py`。
- 测试文件应放在其对应的镜像测试目录下，避免跨目录混放。

## 变更要求

- 新增被测目录时，应同步新增对应测试目录，保持结构可追踪。
- 若调整被测目录结构，应先调整测试目录映射，再修改具体测试实现。
