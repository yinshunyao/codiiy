# coder 编程工具

description: 面向编程任务生成结构化实现草案与代码模板，支持按需创建脚手架目录与基础文件。

支持操作系统: all

## 功能说明
- 输入自然语言或 JSON 任务描述，提取核心 `task`。
- 默认创建脚手架目录，并生成 `README.md` 与代码入口文件。
- 输出统一结构化结果：语言判断、实现步骤、代码模板、落盘结果、风险提示。
- 不直接执行系统命令。

## 输入示例
```json
{
  "task": "实现一个文件写入组件，支持覆盖与追加",
  "language": "python",
  "target_dir": "generated/file_writer_tool",
  "mode": "scaffold"
}
```

## 输出字段
- `status`: `success` 或 `error`
- `result`: 成功时返回草案详情
- `message`: 人类可读执行摘要

## 关键参数
- `mode`: `scaffold`（默认，创建目录与文件）或 `draft`（仅生成草案，不落盘）
- `project_root`: 可选，项目根目录；写入目标必须在该目录内
- `target_dir`: 可选，相对 `project_root` 的目标目录
