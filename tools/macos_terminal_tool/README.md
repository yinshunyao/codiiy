# MacosTerminalTool

## 功能描述

`MacosTerminalTool` 基于 `tools/component_call_tool` 调用 `component.handle.macos_terminal_component`，提供“终端对象”抽象，支持会话化输入输出互操作。

适用场景：
1. 需要保持 shell 上下文的多轮命令执行（如 `cd` 后继续执行）。
2. 需要将“输入命令”和“增量读取输出”拆分处理。
3. 需要在工具层统一管理终端对象生命周期（创建、查询、关闭）。

支持操作系统：macos

## 输入与输出约定

- 统一返回：
  - 成功：`{"success": True, "data": {...}}`
  - 失败：`{"success": False, "error": "错误信息"}`

## API

### `create_terminal_object(cwd: str = "", shell_mode: str = "zsh") -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `cwd` | `str` | `""` | 终端初始工作目录。 |
| `shell_mode` | `str` | `"zsh"` | Shell 类型，如 `zsh`。 |

返回 `data` 字段：`object_id`、`cwd`、`shell_mode`（按实现返回）。

### `input_output(object_id: str, command: str, timeout_seconds: float = 30.0, read_incremental_output: bool = False) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `object_id` | `str` | 必填 | 已创建终端对象 ID。 |
| `command` | `str` | 必填 | 要执行的 shell 命令。 |
| `timeout_seconds` | `float` | `30.0` | 命令执行超时时间。 |
| `read_incremental_output` | `bool` | `False` | 是否按增量模式读取输出。 |

返回 `data` 字段：`output`、`offset`（按实现返回）。

### `run_command(command: str, cwd: str = "", shell_mode: str = "zsh", timeout_seconds: float = 30.0) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `command` | `str` | 必填 | 要执行的 shell 命令。 |
| `cwd` | `str` | `""` | 一次性会话的工作目录。 |
| `shell_mode` | `str` | `"zsh"` | Shell 类型。 |
| `timeout_seconds` | `float` | `30.0` | 命令执行超时时间。 |

返回 `data` 字段：`output`、`exit_code`（按实现返回）。该方法自动创建并关闭会话。

### `read_output(object_id: str, offset: Optional[int] = None, update_offset: bool = True) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `object_id` | `str` | 必填 | 终端对象 ID。 |
| `offset` | `Optional[int]` | `None` | 输出读取起始偏移。 |
| `update_offset` | `bool` | `True` | 是否在返回中更新偏移位置。 |

返回 `data` 字段：`output`、`offset`。

### `close_terminal_object(object_id: str) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `object_id` | `str` | 必填 | 待关闭的终端对象 ID。 |

返回 `data` 字段：`object_id`、`closed`（按实现返回）。

### `list_terminal_objects() -> Dict`

无参数。

返回 `data` 字段：`objects`（终端对象列表，包含 `object_id`、`cwd`、`shell_mode`、`status`）。

## 依赖组件

本工具仅通过 `ComponentCallTool.control_call` 调用以下组件 API：

1. `component.handle.create_macos_terminal_session`
2. `component.handle.run_macos_terminal_command`
3. `component.handle.get_macos_terminal_output`
4. `component.handle.close_macos_terminal_session`

## 使用示例

```python
from tools.macos_terminal_tool import MacosTerminalTool

tool = MacosTerminalTool(auto_install=False)

create_result = tool.create_terminal_object(cwd="", shell_mode="zsh")
if not create_result["success"]:
    raise RuntimeError(create_result["error"])

object_id = create_result["data"]["object_id"]

run_result = tool.input_output(
    object_id=object_id,
    command="pwd && echo hello",
    timeout_seconds=30.0,
)
print(run_result)

incremental = tool.read_output(object_id=object_id)
print(incremental)

close_result = tool.close_terminal_object(object_id=object_id)
print(close_result)
```

## 边界说明

1. 本工具不直接创建 shell 子进程，底层能力由组件负责。
2. 在非 macOS 环境调用时，按组件返回错误透传。
3. 关闭后的对象不可继续输入或读取输出。
4. 工具仅负责对象化管理和调用编排，不负责命令安全审计。
