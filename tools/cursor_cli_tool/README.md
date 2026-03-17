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

## API

### `create_cursor_cli_session(cwd: str = "", shell_mode: str = "zsh", cursor_binary: str = "cursor", check_available: bool = True, check_timeout_seconds: float = 10.0) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `cwd` | `str` | `""` | 会话初始工作目录。 |
| `shell_mode` | `str` | `"zsh"` | Shell 类型。 |
| `cursor_binary` | `str` | `"cursor"` | Cursor CLI 可执行文件名或路径。 |
| `check_available` | `bool` | `True` | 创建后是否立即检测 `cursor` 可用性。 |
| `check_timeout_seconds` | `float` | `10.0` | 可用性检测超时时间。 |

返回 `data` 字段：`object_id`、`cursor_binary`、`available`（按实现返回）。

### `check_cursor_available(object_id: str, timeout_seconds: float = 10.0) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `object_id` | `str` | 必填 | CLI 会话对应的终端对象 ID。 |
| `timeout_seconds` | `float` | `10.0` | 检测命令超时时间。 |

返回 `data` 字段：`available`、`version_output`（按实现返回）。

### `call_cursor(object_id: str, args: str = "", command: str = "", timeout_seconds: float = 120.0, read_incremental_output: bool = False) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `object_id` | `str` | 必填 | CLI 会话对象 ID。 |
| `args` | `str` | `""` | 传给 `cursor` 的参数字符串。 |
| `command` | `str` | `""` | `args` 的兼容别名。 |
| `timeout_seconds` | `float` | `120.0` | 命令执行超时时间。 |
| `read_incremental_output` | `bool` | `False` | 是否增量读取输出。 |

返回 `data` 字段：`output`、`exit_code`、`command`（按实现返回）。

### `call_cursor_with_prompt(object_id: str, prompt: str, args: str = "", timeout_seconds: float = 120.0, read_incremental_output: bool = False) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `object_id` | `str` | 必填 | CLI 会话对象 ID。 |
| `prompt` | `str` | 必填 | Prompt 文本。 |
| `args` | `str` | `""` | 附加参数，如 `--format text`。 |
| `timeout_seconds` | `float` | `120.0` | 命令执行超时时间。 |
| `read_incremental_output` | `bool` | `False` | 是否增量读取输出。 |

返回 `data` 字段：`output`、`exit_code`、`command`（按实现返回）。

### `call_cursor_agent(object_id: str = "", prompt: str = "", model: str = "", mode: str = "", session_id: str = "", workspace: str = "", output_format: str = "stream-json", extra_args: str = "", timeout_seconds: float = 180.0, read_incremental_output: bool = False) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `object_id` | `str` | `""` | 会话对象 ID，空值时自动创建会话。 |
| `prompt` | `str` | `""` | Agent 提示词。 |
| `model` | `str` | `""` | 指定模型，空值走默认。 |
| `mode` | `str` | `""` | 对话模式，如 `ask`/`plan`。 |
| `session_id` | `str` | `""` | 续接已有会话 ID。 |
| `workspace` | `str` | `""` | 指定工作区路径。 |
| `output_format` | `str` | `"stream-json"` | 输出格式。 |
| `extra_args` | `str` | `""` | 额外 CLI 参数。 |
| `timeout_seconds` | `float` | `180.0` | 调用超时时间。 |
| `read_incremental_output` | `bool` | `False` | 是否增量读取输出。 |

返回 `data` 字段：`output`、`parsed`（包含 `session_id`、`usage`、`cost_usd`、`summary`、`error`）、`actual_object_id`、`auto_created_session`（按实现返回）。

### `parse_stream_json_output(output_text: str) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `output_text` | `str` | 必填 | `stream-json/jsonl` 原始输出。 |

返回 `data` 字段：`session_id`、`usage`、`cost_usd`、`summary`、`error`（按可解析结果返回）。

### `get_cursor_session_id(object_id: str) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `object_id` | `str` | 必填 | CLI 会话对象 ID。 |

返回 `data` 字段：`session_id`。

### `close_cursor_cli_session(object_id: str) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `object_id` | `str` | 必填 | 待关闭的 CLI 会话对象 ID。 |

返回 `data` 字段：`object_id`、`closed`（按实现返回）。

### `list_cursor_cli_sessions() -> Dict`

无参数。

返回 `data` 字段：`objects`（Cursor CLI 会话列表）。

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
