# agents/mindforge

`mindforge` 是伙伴编排中的“心法”模块，负责承载可切换推理策略。

## 最新目录逻辑

- 按策略独立目录组织，当前包含：
  - `auto_strategy`：Auto 自动路由策略（按任务复杂度与执行反馈选择/组合策略）。
  - `react_strategy`：ReAct 多步推理与工具调用闭环。
  - `cot_strategy`：CoT 单轮推理策略。
  - `plan_execute_strategy`：Plan-and-Execute 两阶段策略（先规划再逐步执行）。
  - `reflexion_strategy`：Reflexion 反思重试策略（执行后评估，不达标时反思并重试）。
- 每个策略目录都需包含 `README.md`，用于管理端检索摘要与单项导入/导出识别。
- 执行器不在本目录内，仍位于 `core/collector/orchestration/mindforge_runner.py`。

## 运行边界

- 策略层负责推理流程，不负责授权裁剪。
- 授权白名单、候选工具收敛、运行参数装配由执行器负责。
- 模型调用与工具执行统一经由 `tools/mindforge_toolset` 工具集代理，禁止策略层直接调用底层 `component.*`。

## 策略选择

- 编排上下文字段：`mindforge_strategy`
- 默认值：`auto`
- 可选值：
  - `auto`：根据任务复杂度自动路由，支持分层/分阶段策略组合与失败兜底。
  - `react`：使用 ReAct 策略目录能力执行。
  - `cot`：使用 CoT 策略目录能力执行。
  - `plan_execute`：使用 Plan-and-Execute 策略目录能力执行。
  - `reflexion`：使用 Reflexion 反思重试策略目录能力执行。

## 开发约束

- 新增策略时必须新建独立目录，禁止把多个策略混放到同一实现文件中。
- 新增策略目录至少包含：`__init__.py`、`api.py`、`README.md`。
- 新增策略后需同步更新：
  - `agents/mindforge/strategy_factory.py` 策略映射；
  - 对应设计文档中的策略清单与目录说明；
  - 相关单元测试。

