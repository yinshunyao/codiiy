from typing import List

from ..strategy_base import MindforgeStrategy
from .engine import ReActEngine
from .models import ReActEngineConfig, ReActRunResult, ReActTool


class ReActMindforgeStrategy(MindforgeStrategy):
    """ReAct 推理策略。"""

    name = "react"
    requires_tools = True

    def run(
        self,
        user_query: str,
        tools: List[ReActTool],
        config: ReActEngineConfig,
        system_prompt: str = "",
    ) -> ReActRunResult:
        engine = ReActEngine(tools=tools, config=config, system_prompt=system_prompt)
        return engine.run(user_query=str(user_query or "").strip())

