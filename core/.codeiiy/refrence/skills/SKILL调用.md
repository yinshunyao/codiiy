这是一个非常棒的问题！你敏锐地发现了不同 Agent 系统在“技能调用”实现上的差异。

**Cloud Code (通常指 Anthropic 的 Claude Code CLI)** 和 **Cursor** 虽然都使用了 "Skill" 这个概念，但它们的**调用机制、文件结构和触发逻辑**有显著区别。同时，业界还有其他几种主流的 Agent 技能调用模式。

下面我将分两部分回答：首先深度解析 **Cloud Code (Claude Code)** 是如何调用 Skill 的，然后对 **主流 Agent 系统的技能调用机制** 进行整体对比总结。

---

### 第一部分：Cloud Code (Claude Code) 如何调用 Skill？

在 Claude Code (CLI 工具) 中，Skill 的调用机制比 Cursor 更加**显式**和**结构化**。它不仅仅依赖语义匹配，还强烈依赖**文件规范**和**命令前缀**。

#### 1. 核心文件结构
Claude Code 的 Skill 通常存放在用户主目录或项目特定目录下，结构非常严格：
*   **路径**：`~/.claude-code/skills/<skill-name>/` 或项目内的 `.claude-code/skills/`
*   **核心文件**：必须包含 `skill.json` (或 `config.json`) 和 `instructions.md` (或 `prompt.md`)。
    *   `skill.json`：定义技能的元数据（名称、描述、触发命令、参数 schema）。
    *   `instructions.md`：定义具体的执行步骤和 Prompt。

**示例 `skill.json`：**
```json
{
  "name": "security-audit",
  "description": "Performs a security audit based on OWASP Top 10",
  "trigger": "/security-review", 
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Directory to scan" }
    }
  }
}
```

#### 2. 调用方式：显式命令 + 语义增强
Claude Code 支持两种主要的调用方式，且往往结合使用：

*   **方式 A：显式命令触发 (Explicit Command)** —— **这是最主要的方式**
    *   用户在终端或对话框中直接输入定义在 `skill.json` 中的 **Trigger Command**。
    *   **操作**：输入 `/security-review src/`
    *   **机制**：系统解析到 `/` 开头的命令，直接映射到对应的 Skill 文件夹，加载 `instructions.md`，并将后续参数（`src/`）传入。
    *   **特点**：确定性高，用户完全掌控何时调用。

*   **方式 B：Agent 自动发现 (Auto-Discovery)**
    *   当用户没有使用斜杠命令，而是用自然语言描述时（例如：“帮我检查一下代码安全”）。
    *   **机制**：Claude 会读取所有已注册 Skill 的 `name` 和 `description` 字段（来自 `skill.json`），将其作为“可用工具”列表。模型根据语义匹配度，**自主决定**是否调用该 Skill。
    *   **注意**：如果匹配成功，模型通常会**反悔并建议用户使用命令**，或者直接在内部模拟执行该命令的流程。

#### 3. Cloud Code vs Cursor 的关键区别

| 特性 | **Cursor Skills** | **Cloud Code (Claude Code) Skills** |
| :--- | :--- | :--- |
| **主要触发方式** | **隐式**：纯自然语言，靠语义匹配。 | **显式 + 隐式**：推荐用 `/command` 显式触发，也支持语义自动匹配。 |
| **配置文件** | `SKILL.md` (纯 Markdown，结构自由)。 | `skill.json` (严格 JSON Schema) + `instructions.md`。 |
| **参数传递** | 靠模型从对话中提取，非结构化。 | 支持定义严格的 JSON Schema 参数，类似函数调用。 |
| **定位** | 像是“潜意识的专家人格”。 | 像是“可加载的专业插件/脚本”。 |

**总结 Cloud Code 的调用逻辑**：
它是一个**混合模式**。首选是通过 **`/命令`** 直接加载对应的 Skill 文件夹并执行其中的指令脚本；其次才是利用大模型的能力，根据描述自动匹配并“虚拟调用”该技能。

---

### 第二部分：主流 Agent 系统技能调用机制整体分析

放眼整个 AI Agent 领域，技能的调用机制主要分为三大流派。理解这些流派有助于你在不同平台（如 LangChain, AutoGen, Coze, Dify, OpenAI Assistants）上设计技能。

#### 流派一：函数调用派 (Function Calling / Tool Use)
*   **代表**：OpenAI Assistants, LangChain Tools, AutoGen, Microsoft Copilot。
*   **核心逻辑**：
    1.  **注册**：将 Skill 定义为标准的 JSON Schema (名称、描述、参数)。
    2.  **注入**：将这些 Schema 放入 System Prompt 的 `<tools>` 部分。
    3.  **决策**：LLM 输出一个特殊的 JSON 块（如 `{"name": "search", "arguments": {...}}`）。
    4.  **执行**：宿主程序解析 JSON，执行对应的真实代码函数，再将结果返回给 LLM。
*   **优点**：标准化程度高，参数验证严格，易于调试。
*   **缺点**：对于复杂的多步流程，需要将其拆解为多个小函数，或者依赖 LLM 的链式调用能力。
*   **调用方式**：完全由 **LLM 自主决定** 何时调用哪个函数。

#### 流派二：提示词注入派 (Prompt Injection / Context Loading)
*   **代表**：Cursor (主要模式), Claude Code (部分模式), 自定义 Agent。
*   **核心逻辑**：
    1.  **存储**：Skill 是一段长文本（Markdown），包含详细的思维链（CoT）、步骤和约束。
    2.  **检索/加载**：根据用户问题，通过向量检索（RAG）或关键词匹配，找到最相关的 Skill 文本。
    3.  **注入**：将这段长文本**直接拼贴**到当前的对话上下文中（System Prompt 或 User Message）。
    4.  **执行**：LLM “阅读”了这段指令后，自然地按照指令去行动。
*   **优点**：能承载极其复杂的逻辑、背景知识和思维过程，不仅仅是简单的函数调用。
*   **缺点**：消耗 Token 多，检索不准会导致指令错乱。
*   **调用方式**：**语义匹配触发**（隐式）或 **命令触发**（显式加载文本）。

#### 流派三：工作流编排派 (Workflow / Graph Orchestration)
*   **代表**：Coze (扣子), Dify, LangGraph。
*   **核心逻辑**：
    1.  **可视化定义**：用户在界面上画流程图，定义节点（Node）和边（Edge）。每个节点是一个 Skill（插件、LLM 节点、代码节点）。
    2.  **路由引擎**：系统内部有一个路由引擎（Router），根据用户输入判断进入哪个分支。
    3.  **执行**：按照预设的图结构依次执行节点。
*   **优点**：流程可控性最强，适合企业级固定业务流程。
*   **缺点**：灵活性较差，难以处理未预见的复杂情况。
*   **调用方式**：**路由规则匹配** 或 **意图识别节点** 决定走向。

### 综合对比总结表

| 维度 | **函数调用派** (OpenAI/LangChain) | **提示词注入派** (Cursor/Claude Code) | **工作流编排派** (Coze/Dify) |
| :--- | :--- | :--- | :--- |
| **Skill 本质** | 代码函数 (Function) | 文本指令 (Instruction/Prompt) | 流程图节点 (Node) |
| **调用决策者** | LLM (基于 Schema) | LLM (基于语义) 或 用户命令 | 路由引擎 / 预设逻辑 |
| **复杂度承载** | 低/中 (适合原子操作) | **高** (适合复杂思维链) | **极高** (适合多步骤业务流) |
| **参数处理** | 严格 JSON Schema 验证 | 自然语言提取 (模糊) | 变量传递 (结构化) |
| **典型应用场景** | 查天气、搜谷歌、计算器 | 代码重构、全栈开发、复杂分析 | 客服机器人、自动化审批、数据清洗流水线 |
| **开发者体验** | 写代码定义工具 | 写 Markdown 定义流程 | 拖拽连线配置流程 |

### 结论与建议

1.  **对于 Cloud Code (Claude Code)**：
    *   它介于**函数调用**和**提示词注入**之间。它用 `skill.json` 做函数式的元数据定义（支持命令触发），但用 `instructions.md` 做提示词注入（承载复杂逻辑）。
    *   **最佳实践**：在 Cloud Code 中，尽量使用 **`/command`** 显式调用 Skill，这样最稳定；如果是通用建议类技能，可以依赖其自动发现机制。

2.  **对于通用 Agent 开发**：
    *   如果你的 Skill 是**原子操作**（如“查询数据库”、“发送请求”），请使用 **函数调用派**（定义 JSON Schema）。
    *   如果你的 Skill 是**专家经验**（如“如何进行代码审查”、“如何撰写技术文档”），请使用 **提示词注入派**（编写详细的 Markdown 指南，配合 RAG 检索）。
    *   如果你的 Skill 是**固定业务流程**（如“用户注册->发邮件->入库”），请使用 **工作流编排派**。

现在的趋势是**融合**：像 LangGraph 这样的框架正在尝试将“函数调用的灵活性”与“工作流的可控性”结合起来；而 Cursor 和 Claude Code 则在探索如何让“文本指令”具备“工具调用的精确性”。