# 示例输出：从需求到完整 skill

本文件提供一个可直接模仿的“输入需求 -> 输出产物”样例。

## 示例需求

> 创建一个可以把会议纪要需求转成标准 Markdown 文档的 skill。  
> 需要有固定结构（标题、摘要、行动项、风险项），并支持从散乱输入中提取负责人和截止日期。  
> 输出目录放在 `core/tools` 下。  
> 希望带一个脚本用于标准化日期格式。

## 预期生成结果（目录树）

```text
core/tools/meeting-notes-skill/
├── SKILL.md
├── scripts/
│   └── normalize_date.py
└── references/
    └── output-schema.md
```

## 预期生成结果（SKILL.md 示例）

```markdown
---
name: meeting-notes-skill
description: 将会议原始记录整理为标准 Markdown 纪要（标题、摘要、行动项、风险项）并提取负责人与截止日期。用户要求“整理会议纪要”“生成行动项列表”“提取负责人和时间”时使用。
---

# Meeting Notes Skill

## 目标
将非结构化会议输入转成统一格式的 Markdown 纪要，并确保行动项可追踪。

## 输入
- 必需：会议原始文本
- 可选：会议主题、参与人名单、日期格式偏好

## 执行步骤
1. 识别会议主题与关键结论，生成摘要。
2. 提取行动项并补全负责人、截止日期。
3. 对日期执行标准化处理（必要时调用 `scripts/normalize_date.py`）。
4. 按固定结构输出纪要正文。

## 输出
- `meeting-notes.md`
- 若用户要求结构说明，引用 `references/output-schema.md`

## 验收标准
- 输出包含标题、摘要、行动项、风险项四个段落
- 每个行动项包含负责人和截止日期（缺失时明确标注“待补充”）
- 日期格式统一
```

## 预期生成结果（脚本示例）

说明：下面仅示意脚本职责，实际实现按项目环境补齐。

```python
#!/usr/bin/env python3
"""Normalize date strings to YYYY-MM-DD."""

def normalize_date(text: str) -> str:
    # Placeholder: implement date parsing strategy per project requirements.
    return text
```

## 生成时的决策说明

- 需要 `scripts/`：因为日期标准化属于可重复、确定性处理。
- 需要 `references/`：因为输出结构可被复用，适合文档化沉淀。
- 不需要 `assets/`：本需求没有模板文件、图片、静态资源依赖。
