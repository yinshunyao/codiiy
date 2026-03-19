from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AdapterExecutionContext:
    """adapter 执行时的上下文信息。"""

    run_id: str
    companion_name: str
    config: dict = field(default_factory=dict)
    prompt: str = ""
    cwd: str = ""
    env: dict = field(default_factory=dict)
    timeout_sec: int = 0


@dataclass
class AdapterExecutionResult:
    """adapter 执行结果。"""

    exit_code: int | None = None
    signal: str | None = None
    timed_out: bool = False
    error_message: str | None = None
    stdout: str = ""
    stderr: str = ""
    result_json: dict | None = None


@dataclass
class AdapterEnvironmentCheck:
    """单项环境检测结果。"""

    code: str
    level: str  # "info" | "warn" | "error"
    message: str
    hint: str = ""
    detail: str = ""


@dataclass
class AdapterEnvironmentTestResult:
    """adapter 环境检测汇总结果。"""

    adapter_type: str
    status: str  # "pass" | "warn" | "fail"
    checks: list[AdapterEnvironmentCheck] = field(default_factory=list)
    tested_at: str = ""

    def __post_init__(self) -> None:
        if not self.tested_at:
            self.tested_at = datetime.now(timezone.utc).isoformat()

    @staticmethod
    def summarize_status(checks: list[AdapterEnvironmentCheck]) -> str:
        levels = {c.level for c in checks}
        if "error" in levels:
            return "fail"
        if "warn" in levels:
            return "warn"
        return "pass"
