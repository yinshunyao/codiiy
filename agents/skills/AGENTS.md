---

# AGENTS.md — 技能（Skills）开发规范与约束

> 本文件定义了在 `skills/` 目录下开发技能模块时应遵循的通用规范、接口约定、安全约束及最佳实践。所有技能均视为“原子能力单元”，供主智能体（Agent）调用以完成复杂任务。

---

## 1. 技能的基本定义

- **技能（Skill）** 是一个独立、可复用、具有明确输入输出契约的 Python 函数或类方法。
- 每个技能应完成**单一职责**（Single Responsibility），避免功能耦合。
- 技能必须通过 **自然语言描述**（docstring）说明其用途、输入参数、输出格式及副作用。

---

## 2. 技能的目录结构

每个技能应组织为独立子目录，例如：

```
skills/
├── calculator/
│   ├── __init__.py
│   ├── skill.py          # 核心实现
│   └── manifest.yaml     # 元数据描述（可选但推荐）
├── web_search/
│   ├── __init__.ty
│   └── skill.py
└── ...
```

> 推荐使用 `manifest.yaml` 描述技能名称、版本、依赖、权限需求等元信息。

---

## 3. 技能接口规范

### 3.1 函数签名

所有技能函数必须满足以下任一形式：

```python
def skill_name(input: str, **kwargs) -> dict:
    """
    执行某项具体任务。
    
    Args:
        input (str): 用户自然语言指令或结构化 JSON 字符串（由调度器解析后传入）
        **kwargs: 可选上下文参数（如 user_id, session_id, config 等）

    Returns:
        dict: 必须包含以下字段：
            - "status": "success" | "error"
            - "result": 任意可序列化结果（str / dict / list）
            - "message": 人类可读的执行摘要（用于日志或反馈）
    """
```

> 若技能需长期运行或异步处理，应返回 `"status": "pending"` 并提供回调机制或任务ID。

### 3.2 异常处理

- 所有异常必须被捕获并转换为标准错误响应：
  ```python
  return {
      "status": "error",
      "result": None,
      "message": "无法连接网络：timeout"
  }
  ```
- 禁止让未处理异常传播至主调度器。

---

## 4. 安全与权限约束

- **禁止执行任意代码**（如 `eval`, `exec`, `os.system` 等）。
- 涉及外部系统（如文件读写、网络请求、数据库）的技能：
  - 必须声明所需权限（在 `manifest.yaml` 中标注 `permissions: [read_file, internet]`）。
  - 默认以**最小权限原则**运行（如仅限用户专属目录读写）。
- 敏感操作（如删除文件、发送邮件）必须要求**显式用户确认**（通过主 Agent 交互层处理，技能本身不直接弹窗）。

---

## 5. 输入输出规范

- **输入**：统一为字符串（支持 JSON 格式），由调度器负责解析。
- **输出**：必须为 JSON-serializable 的 `dict`，不得包含不可序列化对象（如函数、文件句柄）。
- 鼓励使用结构化输出（如 `{"answer": "42", "source": "wolfram_alpha"}`）而非纯文本。

---

## 6. 测试与验证

- 每个技能必须包含单元测试（`test_skill.py`），覆盖正常路径与典型错误场景。
- 测试用例应模拟真实调度器调用方式（即传入字符串输入）。
- 使用 `pytest` 作为测试框架，纳入 CI 流程。

---

## 7. 日志与可观测性

- 技能内部应使用标准 `logging` 模块记录关键步骤（级别 ≥ INFO）。
- 日志内容不得包含敏感信息（如密码、token）。
- 建议记录：调用时间、输入摘要（脱敏）、耗时、结果状态。

---

## 8. 性能与资源限制

- 单次技能执行时间建议 ≤ 10 秒（可配置超时）。
- 内存占用应可控，避免加载大型模型或缓存全局状态（除非明确设计为状态技能）。
- 高频技能（如时间查询）应支持无状态、快速响应。

---

## 9. 技能注册与发现

- 所有技能需在 `skills/__init__.py` 中导出，或通过自动扫描注册。
- 主 Agent 通过技能名称（如 `"calculator.add"`）动态调用，名称应全局唯一且语义清晰。

---

## 10. 示例：一个合规技能

```python
# skills/calculator/skill.py
import logging
import json

logger = logging.getLogger(__name__)

def calculate(input: str, **kwargs) -> dict:
    try:
        data = json.loads(input)
        expr = data.get("expression", "")
        result = eval(expr, {"__builtins__": {}}, {})  # 安全受限的 eval
        logger.info(f"Evaluated expression: {expr} = {result}")
        return {
            "status": "success",
            "result": str(result),
            "message": f"计算结果为 {result}"
        }
    except Exception as e:
        logger.error(f"Calculation error: {e}")
        return {
            "status": "error",
            "result": None,
            "message": f"表达式无效：{str(e)}"
        }
```

> ⚠️ 注意：实际项目中应使用 `ast.literal_eval` 或专用表达式解析器替代 `eval`。

---

遵循以上规范，可确保你的技能系统具备**安全性、可维护性、可组合性**，为构建强大而可靠的个人全能助理奠定基础。

---