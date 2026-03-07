规则
规则为 Agent 提供系统级指令。它们将提示词、脚本等打包在一起，便于在团队内管理和共享工作流。

Cursor 支持四种类型的规则：

项目规则

存储在 .cursor/rules 中，受版本控制且仅作用于你的代码库。

用户规则

在你的 Cursor 环境中全局生效，供 Agent (聊天) 使用。

团队规则

在仪表盘中集中管理的团队级规则，适用于 Team 和 Enterprise 方案。

AGENTS.md

以 Markdown 格式编写的 Agent 指令，是 .cursor/rules 的简化替代方案。

规则如何工作
大语言模型在各次补全之间不会保留记忆。规则在提示层面提供持久、可复用的上下文。

应用规则时，其内容会被加入到模型上下文的开头。这为 AI 在生成代码、理解修改或协助处理工作流程时提供一致的指导。

项目规则
项目规则存放在 .cursor/rules 目录中的 Markdown 文件里，并纳入版本控制。它们可以通过路径模式限定作用范围、手动触发，或按相关性自动应用。

使用项目规则可以：

固化与你代码库相关的领域知识
自动化项目特定的工作流或模板
统一风格或架构决策
规则文件结构
每条规则对应一个 Markdown 文件，文件名可自定义。Cursor 支持 .md 和 .mdc 扩展名。使用带有 frontmatter 的 .mdc 文件来指定 description 和 globs，以便更精细地控制规则的生效条件。


.cursor/rules/
  react-patterns.mdc       # 带有前置元数据的规则（description, globs）
  api-guidelines.md        # 简单的 markdown 规则
  frontend/                # 在文件夹中组织规则
    components.md
规则结构
每条规则都是一个带有 frontmatter 元数据和内容的 markdown 文件。通过类型下拉菜单控制规则的应用方式，该菜单会更改 description、globs、alwaysApply 属性。

Rule Type	描述
Always Apply	应用于每个聊天会话
Apply Intelligently	当 Agent 根据描述判断其相关时应用
Apply to Specific Files	当文件匹配指定模式时应用
Apply Manually	在聊天中被 @ 提及时应用 (例如 @my-rule)

---
globs:
alwaysApply: false
---
- Use our internal RPC pattern when defining services
- Always use snake_case for service names.
@service-template.ts
创建规则
有两种方式可以创建规则：

在对话中使用 /create-rule：在 Agent 中输入 /create-rule，然后描述你的需求。Agent 会生成带有正确 frontmatter 的规则文件，并将其保存到 .cursor/rules。
在设置中创建：打开 Cursor Settings > Rules, Commands，然后点击 + Add Rule。这会在 .cursor/rules 中创建一个新的规则文件。在设置中可以查看所有规则及其状态。
最佳实践
好的规则应当聚焦、可操作且范围明确。

将规则控制在 500 行以内
将大型规则拆分为多个可组合的规则
提供具体示例或引用相关文件
避免模糊的指导，像撰写清晰的内部文档那样来写规则
在聊天中重复提示时复用规则
引用文件而不是复制其内容——这样可以让规则更简短，并避免在代码变更后规则变得陈旧
编写规则时应避免的事项
整份照搬风格指南：请改用 linter。Agent 已经了解常见的风格规范。
把每一个可能的命令都写进文档：Agent 了解常用工具，比如 npm、git 和 pytest。
为极少出现的边缘情况添加说明：让规则只聚焦在你经常使用的模式上。
重复你代码库中已有的内容：引用规范示例，而不是复制代码。
从简单开始。只有在你发现 Agent 反复犯同样的错误时才添加规则。在你真正理解自己的模式之前，不要过度优化。

把你的规则提交到 Git，这样整个团队都能受益。当你看到 Agent 出错时，就更新对应的规则。你甚至可以在 GitHub issue 或 PR 上标记 @cursor，让 Agent 帮你更新规则。

规则文件格式
每条规则都是一个包含 frontmatter 元数据和正文内容的 Markdown 文件。frontmatter 元数据用于控制规则的应用方式，正文则定义规则本身。


---
description: "This rule provides standards for frontend components and API validation"
alwaysApply: false
---
...rest of the rule content
如果 alwaysApply 为 true，则该规则会应用于每个聊天会话。否则，会将该规则的描述展示给 Cursor Agent，由其决定是否应当应用该规则。

示例

前端组件与 API 校验规范

Express 服务与 React 组件模板

开发流程与文档生成自动化

在 Cursor 中添加新设置

各大提供方和框架都提供了示例。社区贡献的规则散见于各类众包合集和线上代码仓库中。

团队规则
Team 和 Enterprise 方案可以通过 Cursor dashboard 在整个组织范围内创建并强制执行规则。管理员可以配置每条规则对团队成员来说是否为必填/必选项。

团队规则会与其他类型的规则一同生效，并具有更高优先级，以确保在所有项目中维持统一的组织标准。它们为整个团队提供了一种强大的方式，在无需逐一进行设置或配置的情况下，确保一致的编码标准、实践和工作流程。

管理 Team Rules
团队管理员可以直接在 Cursor 仪表板中创建和管理规则：

空的团队规则仪表板，团队管理员可以在其中添加新规则
创建 Team Rules 后，它们会自动应用于所有团队成员，并在仪表板中显示：

团队规则仪表板，显示一条将对所有团队成员生效的团队规则
启用与强制执行
立即启用此规则：选中后，该规则在创建后立即生效。未选中时，该规则会作为草稿保存，在你之后手动启用前不会生效。
强制执行此规则：启用后，该规则会对所有团队成员强制生效，且无法在他们各自的 Cursor 设置中被关闭。未强制执行时，团队成员可以在 Cursor Settings → Rules 的 Team Rules 部分中将该规则关闭。
默认情况下，未强制执行的 Team Rules 可以被用户关闭。使用强制执行此规则来防止用户关闭这些规则。

Team Rules 的格式与应用方式
内容：Team Rules 是自由格式文本，不使用 Project Rules 的文件夹结构。
Glob 模式：Team Rules 支持使用 glob 模式按文件范围生效。当设置了 glob 模式 (例如 **/*.py) 时，规则仅在匹配的文件出现在上下文中时生效。没有 glob 模式的规则适用于每个会话。
适用范围：当某条 Team Rule 被启用 (且未被用户禁用，除非是强制规则) 时，它会被包含在该团队所有代码仓库和项目中的 Agent (Chat) 模型上下文中。
优先级：规则按以下顺序应用：Team Rules → Project Rules → User Rules。所有适用规则会合并；当规则指引冲突时，靠前来源具有更高优先级。
有些团队会将强制规则作为内部合规流程的一部分使用。尽管这是受支持的用法，但 AI 建议不应成为你唯一的安全控制手段。

导入规则
可以从外部来源导入规则，以复用现有配置或引入其他工具的规则。

远程规则 (通过 GitHub)
从你有访问权限的任何 GitHub 仓库 (公共或私有) 直接导入规则。

打开 Cursor Settings → Rules, Commands
点击 + Add Rule (位于 Project Rules 旁) ，然后选择 Remote Rule (GitHub)
粘贴包含该规则的 GitHub 仓库 URL
Cursor 会拉取该规则并将其同步到你的项目中
导入的规则会与其源仓库保持同步，因此远程规则的更新会自动体现在你的项目中。

AGENTS.md
AGENTS.md 是一个用于定义 agent 指令的简单 markdown 文件。将它放在项目根目录中，可作为 .cursor/rules 的一种替代方式，适用于简单直接的用例。

与 Project Rules 不同，AGENTS.md 是不带元数据或复杂配置的纯 markdown 文件。对于只需要简单、易读指令且不想引入结构化规则开销的项目来说，它非常合适。

Cursor 支持在项目根目录和子目录中使用 AGENTS.md。


# Project Instructions
## Code Style
- Use TypeScript for all new files
- Prefer functional components in React
- Use snake_case for database columns
## Architecture
- Follow the repository pattern
- Keep business logic in service layers
改进

嵌套 AGENTS.md 支持
用户规则
用户规则是在 Cursor Settings → Rules 中定义的全局首选项，适用于所有项目。它们供 Agent (Chat) 使用，非常适合用来设定偏好的沟通风格或编码规范：


Please reply in a concise style. Avoid unnecessary repetition or filler language.