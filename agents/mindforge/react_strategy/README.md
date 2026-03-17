# mindforge/react_strategy

ReAct 策略目录（可独立导入/导出）。

## 目录职责

- `api.py`：策略入口（`ReActMindforgeStrategy`）。
- `engine.py`：ReAct 主循环与可选 LangGraph 执行。
- `models.py`：数据结构定义（工具、配置、步骤、结果）。
- `protocol.py`：模型输出解析与文本提取。
- `executor.py`：工具白名单执行封装。

## 协议约束

- 动作模式：`{"thought":"...","action":{"tool":"工具名","kwargs":{...}}}`
- 结束模式：`{"thought":"...","done":true}`
- 一次仅允许一个工具动作，且工具名必须在初始化白名单中。

