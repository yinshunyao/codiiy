# 关联文档
| 类型 | 文档路径 |
|:---|:---|
| 原始需求 | `codiiy/doc/01-or/TOOLS/tool-macos终端对象工具.md` |
| 开发设计 | `codiiy/doc/02-dr/02 control组件化与启停管理设计.md` |

## 测试范围
1. `tools.macos_terminal_tool` 对外仅暴露黑盒主入口（`run_command`）。
2. `run_command` 入参最小可用（仅 `command`）与可选参数（`cwd/shell_mode/timeout_seconds`）。
3. `run_command` 返回结构稳定性（`success/data` 或 `success/error`）。
4. 内部对象化能力对外隔离，不作为工具对外主调用面。
5. `cursor_cli_tool` 复用内部对象化能力的兼容性（回归保障）。

## 测试用例
1. 黑盒接口可用
- 前置条件：工具实例可创建。
- 操作步骤：调用 `run_command(command="pwd")`。
- 预期结果：返回统一结构，包含 `command`、`exit_code`、`stdout`、`stderr`。

2. 单函数入口约束
- 前置条件：工具实例可创建。
- 操作步骤：检查工具对外能力。
- 预期结果：工具集对外主调用函数为 `run_command`，不要求大模型调用对象化多步骤接口。

3. 命令为空校验
- 前置条件：工具实例可创建。
- 操作步骤：调用 `run_command(command="")`。
- 预期结果：返回失败，错误信息可读。

4. 可选参数透传
- 前置条件：工具实例可创建。
- 操作步骤：调用 `run_command(command="pwd", cwd="/tmp", shell_mode="zsh", timeout_seconds=10.0)`。
- 预期结果：参数按预期透传并执行。

5. Cursor CLI 回归
- 前置条件：`cursor_cli_tool` 可实例化。
- 操作步骤：执行 `create_cursor_cli_session/call_cursor/close_cursor_cli_session` 关键路径测试。
- 预期结果：行为与改造前一致，不受黑盒收敛影响。

## 自动化测试标识
1. 工具单测（unittest）
- `test/test_tools/test_macos_terminal_tool/test_macos_terminal_tool.py`

2. Cursor 回归（unittest）
- `test/test_tools/test_cursor_cli_tool/test_cursor_cli_tool.py`

