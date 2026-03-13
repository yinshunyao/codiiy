# agents/mindforge

智能体模块 `mindforge`，当前提供结构化 ReAct 引擎实现。

## 能力说明

- 基于 `component.decide.chat_completion` 做推理决策。
- 基于 `tools/component_call_tool` 做工具调用。
- 支持 ReAct 循环（Thought -> Action -> Observation）。
- 支持可选 `langgraph` 图执行；未安装时自动降级为内置循环。
- 引擎实现位于子目录 `agents/mindforge/react_engine`。

## 快速使用

```python
from agents.mindforge import ReActEngine, ReActEngineConfig, ReActTool

tools = [
  ReActTool(
    name="read_file",
    function_path="component.handle.read_file",
    description="读取文件内容",
  ),
  ReActTool(
    name="search_keyword",
    function_path="component.handle.search_keyword",
    description="按关键字搜索",
  ),
]

engine = ReActEngine(
  tools=tools,
  config=ReActEngineConfig(
    model="qwen-plus",
    config_name="default",
    max_steps=6,
  ),
)

result = engine.run("请先读取 readme.md，然后总结这个项目的目标")
print(result.to_dict())
```

## 输入输出约定

- 模型输出必须是 JSON 对象，并遵循两种形态之一：
  - `{"thought":"...","action":{"tool":"工具名","kwargs":{...}}}`
  - `{"thought":"...","final_answer":"..."}`
- 工具调用仅允许使用初始化时注册的工具名，禁止直接执行任意函数路径。

