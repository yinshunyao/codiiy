---
name: skill-gen
description: 根据需求描述生成完整 Agent Skill（目录、SKILL.md、可选 scripts/references/assets、验收清单）。当用户要求“创建一个 skill”“根据需求做 skill”“补全 skill 结构/内容”或更新已有 skill 时使用。
---

# Skill Generator

## 目标

将用户提供的需求描述，转换为可直接使用的完整 skill 产物，而不是只给建议。

完整产物至少包含：
- `skill-name/SKILL.md`

按需包含：
- `skill-name/scripts/`
- `skill-name/references/`
- `skill-name/assets/`
- `skill-name/agents/openai.yaml`

## 输入要求

如果用户未给全，先补齐最小必要信息：
- 技能目标：要解决什么问题
- 触发场景：什么请求应触发该 skill
- 输出位置：skill 放在哪个目录
- 是否需要脚本/参考文档/资产文件

若用户没有指定技能名，按需求自动生成：
- 小写字母、数字、连字符
- 动词优先，语义清晰
- 不超过 64 字符

## 生成流程

1. 解析需求并拆解复用资产
- 把需求拆成：流程指令、可复用脚本、参考资料、输出模板
- 仅保留能提升后续执行效率的信息，避免冗长背景

2. 设计 skill 结构
- 默认只创建必要目录
- 需要确定性执行时再创建 `scripts/`
- 需要长文档知识时再创建 `references/`
- 仅当最终输出依赖静态资源时创建 `assets/`

3. 编写 `SKILL.md`
- Frontmatter 仅包含 `name` 与 `description`
- `description` 必须同时描述“做什么 + 何时使用”
- 正文使用可执行步骤（祈使句/动作导向）
- 不写与执行无关的过程性说明

4. 按需补充资源
- 在 `scripts/` 放可重复执行、可验证的脚本
- 在 `references/` 放详细规范、Schema、术语、策略
- 在 `assets/` 放模板、示例资源、静态文件

5. 验收
- 目录与文件齐全
- frontmatter 合规
- 指令可直接执行且无歧义
- 不创建无关文档（如 README、CHANGELOG）

## 示例输出

当你不确定“完整产物应该长什么样”时，先读取：
- `references/example-output.md`

使用方式：
- 先对照“示例需求”理解输入粒度
- 再复用“目录树 + SKILL.md 示例”的组织方式
- 最后按当前需求替换领域词汇、步骤和验收标准，避免生搬硬套

## SKILL.md 编写模板

```markdown
---
name: <skill-name>
description: <它做什么，以及在什么场景下应触发>
---

# <Skill Title>

## 目标
<一句话描述交付结果>

## 输入
<列出必需输入与可选输入>

## 执行步骤
1. <步骤 1>
2. <步骤 2>
3. <步骤 3>

## 输出
- <明确文件路径或产物结构>

## 验收标准
- <可检查、可判定的标准>
```

## 生成完整 skill 的最小检查清单

- 已创建与 `name` 一致的目录名
- 已写入合法 frontmatter（仅 `name`、`description`）
- `description` 含触发关键词与使用场景
- 正文包含输入、步骤、输出、验收标准
- 仅在必要时创建 `scripts/`、`references/`、`assets/`
- 所有路径使用相对 skill 根目录的引用

## 质量约束

- 优先复用已有实现与已有文档，不重复造轮子
- 内容简洁，避免长篇概念解释
- 输出要“可执行”，不是“思路草案”
- 若是更新已有 skill，保留原有可用内容并增量修改
