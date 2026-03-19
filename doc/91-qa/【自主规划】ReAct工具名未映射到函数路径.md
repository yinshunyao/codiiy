## 问题描述
在 ReAct 执行阶段，模型返回了工具调用：

```json
{
  "tool_name": "macos_terminal_tool",
  "function_path": "",
  "parent_step_id": "step_6",
  "parent_executor": "mindforgeRunner"
}
```

执行结果出现：
- `observation_preview: "未知工具: macos_terminal_tool"`
- 错误：`工具未注册: macos_terminal_tool`

该问题导致执行器未实际调用工具函数，任务在可执行场景中提前失败。

## 关联文档
| 类型 | 文档路径 |
|:---|:---|
| 原始需求 | `codiiy/doc/01-or/复杂任务理解和处理的方案.md` |
| 开发设计 | `codiiy/doc/02-dr/01 会话原始需求收集系统设计.md` |
| 测试设计 | `codiiy/doc/03-tr/01 会话原始需求收集系统测试需求.md` |

## 根因分析
1. `mindforge_runner` 构建 ReAct 工具候选时只依赖“query 检索命中”，当检索未命中某工具集函数时，该工具集不会进入本轮注册列表。
2. ReAct 模型可能输出工具集级别别名（如 `macos_terminal_tool`），但该别名只有在对应函数已注册时才能映射到 `tools.<toolset>.<function>`。
3. 动态函数发现的代码反射阶段曾纳入工具目录中的内部辅助类方法，放大了别名歧义风险，不利于稳定从工具名映射到唯一函数路径。

## 涉及文件
- `codiiy/core/collector/orchestration/mindforge_runner.py`
  - ReAct 工具构建增加“白名单工具集全量函数兜底”，即使 query 检索未命中，也会把已授权工具集函数纳入注册。
- `codiiy/core/collector/orchestration/capability_search.py`
  - 工具函数代码反射仅提取工具主类（`<ToolsetName>Tool`）公共方法，避免内部对象类方法污染调度目录。
  - 新增按工具集列出函数条目能力，供执行器兜底注册使用。
- `codiiy/test/test_core/test_collector/test_orchestration/test_orchestration.py`
  - 新增回归测试覆盖“检索未命中时仍能注册白名单工具函数”与“仅提取主类方法”。

## 设计约束更新
- ReAct 执行器只调度 `tools.*` 函数路径；工具集级别别名必须可确定映射到已注册函数。
- 候选工具注册不能只依赖 query 命中，必须保证白名单工具集在执行阶段具备最小可执行函数集。
