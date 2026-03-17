# RuleReader 分层规则读取工具

## 功能描述

`RuleReader` 用于从给定路径向上逐级读取 `AGENTS.md`，并返回“就近优先”的规则结果，支持用于系统提示词构建。

支持操作系统：macos, linux, windows

## 优先级

- 最近层级的 `AGENTS.md` 优先级最高
- 更上层 `AGENTS.md` 优先级更低
- 返回顺序：高优先级 -> 低优先级

## 使用方式

```python
from tools.rule_reader import RuleReader

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

## 输入与输出约定

- 输入：
  - `target_path`：目标文件或目录路径（必填）。
  - `stop_at`：停止向上扫描的目录（可选，包含该目录）。
  - `encoding`：读取文件编码（默认 `utf-8`）。
- 成功返回：
  - `{"success": True, "data": {"rules": [...], "merged_rules": "...", ...}}`
- 失败返回：
  - `{"success": False, "error": "错误信息"}`

## 依赖组件

- 本 tool 不直接调用任何 `component` API。
- 若未来需要查询或调用组件能力，必须通过 `tools/component_call_tool`，不能直接调用 `component` 代码。

## 返回结构示例

成功时：

```python
{
    "success": True,
    "data": {
        "target_path": "...",
        "stop_at": "...",
        "rules": [
            {"path": ".../doc/01-or/AGENTS.md", "distance": 0, "content": "..."},
            {"path": ".../AGENTS.md", "distance": 2, "content": "..."}
        ],
        "merged_rules": "...",
        "resolution_order": "优先级从高到低：距离目标路径最近的 AGENTS.md -> 更上层 AGENTS.md。"
    }
}
```

失败时：

```python
{"success": False, "error": "错误信息"}
```

## 边界说明

1. 仅负责读取并合并分层 `AGENTS.md` 规则，不负责组件能力编排。
2. 不处理规则语义冲突，仅按路径距离返回“就近优先”结果。
3. 依赖目标路径与文件系统状态，路径不存在会直接失败返回。
