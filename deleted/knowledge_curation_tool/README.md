# knowledge_curation_tool

## 功能描述
`knowledge_curation_tool` 用于本地知识库整理与分析，提供以下能力：
- 扫描知识项（Markdown/TXT）
- 生成知识库健康分析
- 输出知识关联建议
- 检测重复内容候选
- 生成 Markdown 优化报告

适用场景：
- 定期巡检知识库质量
- 识别可合并内容与潜在关联
- 为人工整理提供候选清单

## 输入与输出
主要类：`KnowledgeCurationTool`

统一返回约定：
- 成功：`{"success": True, "data": ...}`
- 失败：`{"success": False, "error": "..."}`

核心方法：
- `scan_items(knowledge_dir)`
- `analyze_health(knowledge_dir, stale_days=180)`
- `suggest_links(knowledge_dir, min_shared_tokens=2, min_similarity=0.35, top_k=3)`
- `detect_duplicates(knowledge_dir, similarity_threshold=0.9)`
- `generate_report(knowledge_dir, output_dir, report_name=None)`

## 依赖组件
本 tool 不直接调用组件 API。

## 使用示例
```python
from tools.knowledge_curation_tool import KnowledgeCurationTool

tool = KnowledgeCurationTool()

health = tool.analyze_health(knowledge_dir="doc/01-or")
print(health)

report = tool.generate_report(
    knowledge_dir="doc/01-or",
    output_dir="data/temp",
    report_name="knowledge_weekly.md",
)
print(report)
```

## 边界说明
- 当前基于关键词与字符串相似度，不包含语义向量检索。
- 仅处理 `.md/.txt` 文件。
- 报告输出用于“建议”，不自动改写原文档。
