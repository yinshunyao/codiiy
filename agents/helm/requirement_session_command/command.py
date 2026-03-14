from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RequirementTransitionDecision:
    """原始需求会话阶段流转决策结果。"""

    should_enter_organizing: bool
    should_mark_completed: bool


class RequirementSessionCommand:
    """
    原始需求收集流程号令。

    负责会话阶段流转判定与用户确认语义识别，供 Django 聊天流程复用。
    """

    DEFAULT_ORGANIZE_CONFIRM_KEYWORDS = (
        "说完了",
        "描述完了",
        "结束了",
        "完成了",
        "需求清楚了",
    )
    DEFAULT_COMPLETE_CONFIRM_KEYWORDS = (
        "确认完成",
        "完成了",
    )

    def __init__(
        self,
        organize_confirm_keywords: Iterable[str] = (),
        complete_confirm_keywords: Iterable[str] = (),
    ):
        organize_candidates = tuple(organize_confirm_keywords) or self.DEFAULT_ORGANIZE_CONFIRM_KEYWORDS
        complete_candidates = tuple(complete_confirm_keywords) or self.DEFAULT_COMPLETE_CONFIRM_KEYWORDS
        self.organize_confirm_keywords = tuple(
            keyword.strip() for keyword in organize_candidates if str(keyword).strip()
        )
        self.complete_confirm_keywords = tuple(
            keyword.strip() for keyword in complete_candidates if str(keyword).strip()
        )

    def is_user_confirmed_for_organize(self, user_content: str) -> bool:
        return self._contains_any_keyword(user_content, self.organize_confirm_keywords)

    def is_user_confirmed_for_complete(self, user_content: str) -> bool:
        return self._contains_any_keyword(user_content, self.complete_confirm_keywords)

    def decide_transition(self, phase: str, user_content: str, analysis_is_complete: bool) -> RequirementTransitionDecision:
        should_enter_organizing = (
            phase == "collecting"
            and analysis_is_complete
            and self.is_user_confirmed_for_organize(user_content)
        )
        should_mark_completed = (
            phase == "organizing"
            and self.is_user_confirmed_for_complete(user_content)
        )
        return RequirementTransitionDecision(
            should_enter_organizing=should_enter_organizing,
            should_mark_completed=should_mark_completed,
        )

    @staticmethod
    def _contains_any_keyword(content: str, keywords: Iterable[str]) -> bool:
        normalized = (content or "").strip()
        if not normalized:
            return False
        return any(keyword in normalized for keyword in keywords)
