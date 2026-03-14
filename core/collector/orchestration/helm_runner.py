from typing import Dict, Tuple

from agents.helm.requirement_session_command import RequirementSessionCommand

from .protocol import STEP_STATUS_SUCCESS


class HelmRunner:
    """号令执行器：提供流程决策能力。"""

    def __init__(self):
        self.command = RequirementSessionCommand()

    def run(self, query: str, phase: str = "collecting") -> Tuple[str, Dict]:
        content = str(query or "").strip()
        analysis_is_complete = self.command.is_user_confirmed_for_organize(content)
        decision = self.command.decide_transition(
            phase=str(phase or "collecting").strip() or "collecting",
            user_content=content,
            analysis_is_complete=analysis_is_complete,
        )
        return STEP_STATUS_SUCCESS, {
            "phase": phase,
            "analysis_is_complete": analysis_is_complete,
            "decision": {
                "should_enter_organizing": bool(decision.should_enter_organizing),
                "should_mark_completed": bool(decision.should_mark_completed),
            },
        }

