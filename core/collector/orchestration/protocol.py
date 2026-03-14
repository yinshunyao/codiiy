import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List


STEP_TYPE_AGENT = "agent"
STEP_TYPE_COMMAND = "command"
STEP_TYPE_TOOL = "tool"
STEP_TYPE_SUMMARIZE = "summarize"

STEP_STATUS_SUCCESS = "success"
STEP_STATUS_FAILED = "failed"
STEP_STATUS_SKIPPED = "skipped"


@dataclass
class PlanStep:
    step_id: str
    step_type: str
    target: str
    input: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_type": self.step_type,
            "target": self.target,
            "input": self.input,
            "depends_on": self.depends_on,
        }


@dataclass
class ExecutionPlan:
    plan_id: str
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    final_strategy: str = "synthesize_all"

    @classmethod
    def new_plan(cls, goal: str) -> "ExecutionPlan":
        return cls(plan_id=str(uuid.uuid4()), goal=str(goal or "").strip())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [step.to_dict() for step in self.steps],
            "final_strategy": self.final_strategy,
        }


@dataclass
class StepResult:
    step_id: str
    status: str
    output: Any = None
    error: str = ""
    duration_ms: int = 0
    executor: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "executor": self.executor,
        }


@dataclass
class OrchestrationResult:
    success: bool
    final_answer: str = ""
    plan: Dict[str, Any] = field(default_factory=dict)
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    active_agent: str = ""
    tool_events: List[Dict[str, Any]] = field(default_factory=list)
    token_usage: Dict[str, int] = field(default_factory=dict)
    error: str = ""
    fallback_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "final_answer": self.final_answer,
            "plan": self.plan,
            "step_results": self.step_results,
            "active_agent": self.active_agent,
            "tool_events": self.tool_events,
            "token_usage": self.token_usage,
            "error": self.error,
            "fallback_used": self.fallback_used,
        }


def now_ms() -> int:
    return int(time.time() * 1000)

