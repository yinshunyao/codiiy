# agents/helm/requirement_session_command

原始需求收集流程号令组件，用于统一管理聊天阶段流转与确认机制。

## 组件职责

- 封装会话阶段状态机判定：`collecting -> organizing -> completed`。
- 封装用户确认语义识别（进入整理、确认完成）。
- 提供稳定可复用接口，避免在业务视图中硬编码关键词和流转条件。

## 对外接口

- `RequirementSessionCommand.is_user_confirmed_for_organize(user_content)`
- `RequirementSessionCommand.is_user_confirmed_for_complete(user_content)`
- `RequirementSessionCommand.decide_transition(phase, user_content, analysis_is_complete)`

## 集成示例

```python
from agents.helm.requirement_session_command import RequirementSessionCommand

command = RequirementSessionCommand()
decision = command.decide_transition(
    phase="collecting",
    user_content="需求描述完了",
    analysis_is_complete=True,
)
if decision.should_enter_organizing:
    # 进入整理阶段
    pass
```

## 复用建议

- 其他入口（非聊天页面）如需执行相同的阶段流转逻辑，应直接复用本号令。
- 关键词可在实例化 `RequirementSessionCommand` 时按场景扩展，不建议在调用方散落定义。
