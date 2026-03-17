from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ReActTool:
    """ReAct 工具定义。"""

    name: str
    function_path: str
    description: str = ""


@dataclass
class ReActStepRecord:
    """单步执行记录。"""

    step: int
    thought: str = ""
    action: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    raw_model_output: str = ""
    error: str = ""
    token_usage: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReActRunResult:
    """ReAct 运行结果。"""

    success: bool
    final_answer: str = ""
    steps: List[ReActStepRecord] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "final_answer": self.final_answer,
            "steps": [asdict(item) for item in self.steps],
            "error": self.error,
        }


@dataclass
class ReActEngineConfig:
    """ReAct 引擎配置。"""

    model: str = "qwen-plus"
    config_name: str = "default"
    api_key: Optional[str] = None
    max_steps: int = 8
    temperature: float = 0.2
    max_tokens: int = 1024
    use_langgraph_if_available: bool = True
    max_same_failure_repeats: int = 2
    stop_on_non_retryable_failure: bool = True
    stop_checker: Optional[Callable[[], bool]] = None
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None

