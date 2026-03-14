# mindforge/react_engine

`mindforge` 模块下的 ReAct 引擎实现目录，采用结构化解耦设计。

## 目录职责

- `models.py`：定义引擎数据结构（工具定义、配置、步骤记录、运行结果）。
- `protocol.py`：解析模型 JSON 输出协议与模型返回文本提取。
- `executor.py`：工具白名单校验与 `ComponentCallTool` 调用封装。
- `engine.py`：主执行流程（循环执行 + LangGraph 可选执行）。
- `__init__.py`：统一导出公共 API。

## 快速使用

```python
from agents.mindforge.react_engine import ReActEngine, ReActEngineConfig, ReActTool

engine = ReActEngine(
    tools=[
        ReActTool(
            name="read_file",
            function_path="component.handle.read_file",
            description="读取文件内容",
        )
    ],
    config=ReActEngineConfig(max_steps=6),
)

result = engine.run("读取 readme.md 并总结")
print(result.to_dict())
```

## 协议约束

- 动作模式：`{"thought":"...","action":{"tool":"工具名","kwargs":{...}}}`
- 结束模式：`{"thought":"...","done":true}`
- 一次仅允许一个工具动作，且工具名必须在初始化白名单中。
- `final_answer` 由执行引擎基于 `steps[].observation` 自动组装，模型不负责拼接长结果文本。
