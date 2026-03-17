# mindforge/plan_execute_strategy

Plan-and-Execute（规划-执行）策略目录（可独立导入/导出）。

## 目录职责

- `api.py`：策略入口（`PlanExecuteMindforgeStrategy`）。
- `__init__.py`：公共导出。

## 执行约束

- 先规划后执行：先由模型一次性生成任务步骤，再按步骤逐条执行。
- 执行阶段每个子任务复用 ReAct 工具闭环（可调用授权工具）。
- 模型调用统一经由 `tools/mindforge_toolset` 转发，不在策略层直连 `component.*`。
- 返回结构与 mindforge 运行结果保持一致（`success/final_answer/steps/error`）。

