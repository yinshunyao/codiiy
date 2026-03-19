# MacosTerminalTool

## 功能描述

`MacosTerminalTool` 是面向大模型调用的黑盒终端工具，对外只提供一个主函数 `run_command`：

- 输入：一条命令；
- 输出：执行结果（退出码、标准输出等）。

工具内部会自动处理会话创建、命令执行、输出回收和会话关闭，调用方无需感知终端对象生命周期。

支持操作系统：macos

## 输入与输出约定

- 成功：`{"success": True, "data": {...}}`
- 失败：`{"success": False, "error": "错误信息"}`

## API

### `run_command(command: str, cwd: str = "", shell_mode: str = "zsh", timeout_seconds: float = 30.0) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `command` | `str` | 必填 | 要执行的 shell 命令。 |
| `cwd` | `str` | `""` | 执行命令的工作目录。 |
| `shell_mode` | `str` | `"zsh"` | Shell 类型。 |
| `timeout_seconds` | `float` | `30.0` | 命令执行超时时间。 |

返回 `data` 字段至少包含：`command`、`exit_code`、`stdout`、`stderr`。

## 依赖组件

内部通过 `tools/component_call_tool.ComponentCallTool.control_call` 间接调用组件能力，调用方无需直接接触组件 API。

## 使用示例

```python
from tools.macos_terminal_tool import MacosTerminalTool

tool = MacosTerminalTool(auto_install=False)
result = tool.run_command(command="pwd")
print(result)
```

## 边界说明

1. 工具层不直接管理 shell 子进程，底层执行依赖组件能力。
2. 在非 macOS 环境调用时，按组件错误透传。
3. 该工具定位为黑盒执行接口，不对外暴露对象化会话方法。
