## 问题描述
ReAct 工具调用日志显示已命中工具函数：

```json
{
  "tool_name": "macos_terminal_tool_run_command",
  "function_path": "tools.macos_terminal_tool.run_command"
}
```

但执行事件里 `observation_preview` 为 `"null"`，未返回真实命令执行结果。

## 关联文档
| 类型 | 文档路径 |
|:---|:---|
| 原始需求 | `codiiy/doc/01-or/复杂任务理解和处理的方案.md` |
| 开发设计 | `codiiy/doc/02-dr/01 会话原始需求收集系统设计.md` |
| 测试设计 | `codiiy/doc/03-tr/01 会话原始需求收集系统测试需求.md` |

## 根因分析
`ReActToolExecutor.execute_tool` 只按 `call_result.data.result` 读取工具输出。  
当工具返回结构为 `{"success": true, "data": {...}}`（无 `result` 嵌套）时，执行器取值为 `None`，最终 `safe_json_dumps(None)` 变成 `"null"`。

## 涉及文件
- `codiiy/agents/mindforge/react_strategy/executor.py`
  - 工具输出解析改为兼容两种结构：
    1. `data.result`
    2. 直接 `data`
- `codiiy/test/test_control/test_agents/test_react_engine.py`
  - 新增回归：当工具返回直接 `data` 结构时，`observation` 不得为 `null`。

## 设计约束更新
- ReAct 工具执行器必须兼容 `CapabilityDispatcher` 工具返回结构差异，不得因返回包装形态差异丢失观测结果。
