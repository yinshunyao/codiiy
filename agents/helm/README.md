# agents/helm

`helm`（号令）智能体模块目录，用于承载循环与状态机逻辑相关的 agent 组件。

## 目录定位

- 聚焦“流程调度、循环控制、状态机编排”类能力。
- 组件级实现建议按子目录拆分，避免单文件堆叠复杂逻辑。
- 与 `mindforge` 模块解耦，保持职责边界清晰。

## 建议结构

- `agents/helm/<agent_component>/`
  - `__init__.py`
  - `README.md`
  - `*.py`（循环、状态迁移、调度逻辑）

## 当前组件

- `requirement_session_command`：原始需求收集流程号令，封装会话阶段流转与用户确认机制。
