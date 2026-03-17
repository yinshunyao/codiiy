# mindforge/reflexion_strategy

Reflexion（反思机制）策略目录（可独立导入/导出）。

## 目录职责

- `api.py`：策略入口（`ReflexionMindforgeStrategy`）。
- `__init__.py`：公共导出。

## 执行约束

- 执行器：每轮执行复用 `ReActEngine` 完成工具调用闭环。
- 反思器：每轮执行后调用模型评估“是否已达成目标”。
- 记忆模块：记录失败原因与改进建议，注入下一轮系统提示。
- 重试策略：仅在未达成目标且仍有重试预算时进入下一轮。
- 返回结构与 mindforge 运行结果保持一致（`success/final_answer/steps/error`）。

