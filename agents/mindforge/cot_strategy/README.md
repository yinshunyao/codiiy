# mindforge/cot_strategy

CoT 策略目录（可独立导入/导出）。

## 目录职责

- `api.py`：策略入口（`CoTMindforgeStrategy`）。
- `__init__.py`：公共导出。

## 执行约束

- 单轮推理：不进入 ReAct 多步工具循环。
- 模型调用统一经由 `tools/mindforge_toolset` 转发，不在策略层直连 `component.*`。
- 返回结构与 mindforge 运行结果保持一致（`success/final_answer/steps/error`）。

