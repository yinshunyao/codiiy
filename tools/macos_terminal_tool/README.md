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
- 关键 API：
  - `create_terminal_object(cwd="", shell_mode="zsh")`
  - `input_output(object_id, command, timeout_seconds=30.0, read_incremental_output=False)`
  - `read_output(object_id, offset=None, update_offset=True)`
  - `close_terminal_object(object_id)`
  - `list_terminal_objects()`

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
