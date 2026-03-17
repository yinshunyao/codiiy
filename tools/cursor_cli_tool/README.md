# CursorCliTool

## 功能描述

`CursorCliTool` 基于 `tools/macos_terminal_tool` 复用终端会话，提供 Cursor CLI 的会话化调用能力，用于将代码开发任务委托给 Cursor 执行。

适用场景：
1. 需要在固定 `cwd` 下连续调用 `cursor` 命令完成代码开发任务；
2. 需要统一封装 Cursor CLI 可用性检测、调用与错误格式；
3. 需要通过 prompt 快捷方式执行 `cursor --print`；
4. 需要解析 `stream-json/jsonl` 输出并提取 `session_id`、token 用量与摘要信息。

当前智能体可用性：
1. 当前仓库的智能体执行链路已支持直接调取本工具；
2. 仍受伙伴权限白名单与工具集启停状态约束。

支持操作系统：macos

## 输入与输出约定

- 统一返回：
  - 成功：`{"success": True, "data": {...}}`
  - 失败：`{"success": False, "error": "错误信息"}`
- 关键 API：
  - `create_cursor_cli_session(cwd="", shell_mode="zsh", cursor_binary="cursor", check_available=True)`
  - `check_cursor_available(object_id, timeout_seconds=10.0)`
  - `call_cursor(object_id, args="", command="", timeout_seconds=120.0, read_incremental_output=False)`（`command` 为兼容别名，内部等价映射到 `args`）
  - `call_cursor_with_prompt(object_id, prompt, args="", timeout_seconds=120.0, read_incremental_output=False)`
  - `call_cursor_agent(object_id, prompt, model="", mode="", session_id="", workspace="", output_format="stream-json", extra_args="", timeout_seconds=180.0, read_incremental_output=False)`
  - `parse_stream_json_output(output_text)`
  - `get_cursor_session_id(object_id)`
  - `close_cursor_cli_session(object_id)`
  - `list_cursor_cli_sessions()`

## 依赖组件

本工具不直接调用组件 API。

终端能力通过 `tools/macos_terminal_tool.MacosTerminalTool` 间接复用，底层组件调用仍由该工具通过 `tools/component_call_tool` 统一处理。

## 使用示例

```python
from tools.cursor_cli_tool import CursorCliTool

tool = CursorCliTool(auto_install=False)

create_result = tool.create_cursor_cli_session(cwd="", shell_mode="zsh")
if not create_result["success"]:
    raise RuntimeError(create_result["error"])

object_id = create_result["data"]["object_id"]

run_result = tool.call_cursor_with_prompt(
    object_id=object_id,
    prompt="请总结当前目录下 README.md 的要点",
    args="--format text",
)
print(run_result)

close_result = tool.close_cursor_cli_session(object_id=object_id)
print(close_result)
```

## 边界说明

1. 当前版本依赖 `MacosTerminalTool`，仅支持 macOS。
2. 该工具按“命令调用”模型工作，不托管长期占用式 TTY 交互进程。
3. 当 Cursor CLI 未安装、命令返回非零退出码时，返回失败并透传可读错误。
4. 会话关闭后不可继续调用，需重新创建会话。
5. `call_cursor_agent` 在 `object_id` 缺失或无效时会自动创建会话并继续执行，返回中会补充 `actual_object_id` 与 `auto_created_session`。
6. `call_cursor/call_cursor_with_prompt/check_cursor_available/get_cursor_session_id/close_cursor_cli_session` 仍要求有效 `object_id`，不会自动兜底。
7. 仅对可解析的 JSON 事件提取结构化字段，原始输出仍保留在 `data.output`。
