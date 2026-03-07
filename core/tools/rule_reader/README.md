# RuleReader 分层规则读取工具

## 功能

`RuleReader` 用于从给定路径向上逐级读取 `rules.md`，并返回“就近优先”的规则结果，支持用于系统提示词构建。

## 优先级

- 最近层级的 `rules.md` 优先级最高
- 更上层 `rules.md` 优先级更低
- 返回顺序：高优先级 -> 低优先级

## 使用方式

```python
from core.tools.rule_reader import RuleReader

reader = RuleReader()
result = reader.read_hierarchical_rules(
    target_path="/path/to/project/doc/01-or",
    stop_at="/path/to/project",
)

if result["success"]:
    merged_rules = result["data"]["merged_rules"]
    rules = result["data"]["rules"]
else:
    print(result["error"])
```

## 返回结构

成功时：

```python
{
    "success": True,
    "data": {
        "target_path": "...",
        "stop_at": "...",
        "rules": [
            {"path": ".../doc/01-or/rules.md", "distance": 0, "content": "..."},
            {"path": ".../rules.md", "distance": 2, "content": "..."}
        ],
        "merged_rules": "...",
        "resolution_order": "优先级从高到低：距离目标路径最近的 rules.md -> 更上层 rules.md。"
    }
}
```

失败时：

```python
{"success": False, "error": "错误信息"}
```
