from .auto_strategy import AutoMindforgeStrategy
from .cot_strategy import CoTMindforgeStrategy
from .plan_execute_strategy import PlanExecuteMindforgeStrategy
from .react_strategy import ReActMindforgeStrategy
from .strategy_base import MindforgeStrategy

try:
    from .reflexion_strategy import ReflexionMindforgeStrategy
except Exception:
    ReflexionMindforgeStrategy = None  # type: ignore[assignment]

_STRATEGY_MAP = {
    "auto": AutoMindforgeStrategy,
    "react": ReActMindforgeStrategy,
    "cot": CoTMindforgeStrategy,
    "plan_execute": PlanExecuteMindforgeStrategy,
}
if ReflexionMindforgeStrategy is not None:
    _STRATEGY_MAP["reflexion"] = ReflexionMindforgeStrategy


def build_mindforge_strategy(strategy_name: str) -> MindforgeStrategy:
    key = str(strategy_name or "react").strip().lower() or "react"
    strategy_cls = _STRATEGY_MAP.get(key) or ReActMindforgeStrategy
    return strategy_cls()

