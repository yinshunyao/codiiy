from __future__ import annotations

import os
import shutil
import subprocess

from adapter.base import BaseAdapter
from adapter.types import (
    AdapterEnvironmentCheck,
    AdapterEnvironmentTestResult,
    AdapterExecutionContext,
    AdapterExecutionResult,
)


class ProcessAdapter(BaseAdapter):
    """通过命令行子进程执行外部 agent 程序。"""

    adapter_type = "process"
    label = "通用命令行"
    config_doc = (
        "command (str, 必填): 要执行的命令\n"
        "args (list[str], 可选): 命令参数\n"
        "cwd (str, 可选): 工作目录\n"
        "env (dict, 可选): 额外环境变量\n"
        "timeout_sec (int, 可选): 超时秒数，0=不限\n"
        "grace_sec (int, 可选): SIGTERM 宽限秒数，默认 15\n"
    )

    def execute(self, context: AdapterExecutionContext) -> AdapterExecutionResult:
        config = context.config or {}
        command = str(config.get("command", "") or "").strip()
        if not command:
            return AdapterExecutionResult(
                exit_code=1,
                error_message="process adapter: command 不能为空",
            )

        args_raw = config.get("args", [])
        if isinstance(args_raw, str):
            args = [a.strip() for a in args_raw.split(",") if a.strip()]
        elif isinstance(args_raw, list):
            args = [str(a) for a in args_raw]
        else:
            args = []

        cwd = str(config.get("cwd", "") or context.cwd or "").strip() or None
        env_config = config.get("env") or {}
        env = {**os.environ, **context.env}
        for k, v in env_config.items():
            if isinstance(v, str):
                env[k] = v

        timeout_sec = int(config.get("timeout_sec", 0) or context.timeout_sec or 0)
        timeout = timeout_sec if timeout_sec > 0 else None

        cmd = [command] + args
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                input=context.prompt if context.prompt else None,
            )
            return AdapterExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                error_message=(
                    f"进程退出码 {proc.returncode}" if proc.returncode != 0 else None
                ),
            )
        except subprocess.TimeoutExpired:
            return AdapterExecutionResult(
                exit_code=None,
                timed_out=True,
                error_message=f"命令执行超时（{timeout_sec}s）",
            )
        except FileNotFoundError:
            return AdapterExecutionResult(
                exit_code=127,
                error_message=f"命令未找到: {command}",
            )
        except Exception as exc:
            return AdapterExecutionResult(
                exit_code=1,
                error_message=f"执行异常: {exc}",
            )

    def test_environment(self, config: dict) -> AdapterEnvironmentTestResult:
        checks: list[AdapterEnvironmentCheck] = []
        command = str(config.get("command", "") or "").strip()

        if not command:
            checks.append(AdapterEnvironmentCheck(
                code="process_command_missing",
                level="error",
                message="process adapter 需要配置 command。",
                hint="设置 command 为可执行的命令路径。",
            ))
        else:
            checks.append(AdapterEnvironmentCheck(
                code="process_command_present",
                level="info",
                message=f"配置的命令: {command}",
            ))
            if shutil.which(command):
                checks.append(AdapterEnvironmentCheck(
                    code="process_command_resolvable",
                    level="info",
                    message=f"命令可执行: {command}",
                ))
            else:
                checks.append(AdapterEnvironmentCheck(
                    code="process_command_unresolvable",
                    level="error",
                    message=f"命令不可执行或未在 PATH 中找到: {command}",
                    detail=command,
                ))

        cwd = str(config.get("cwd", "") or "").strip()
        if cwd:
            if os.path.isdir(cwd):
                checks.append(AdapterEnvironmentCheck(
                    code="process_cwd_valid",
                    level="info",
                    message=f"工作目录有效: {cwd}",
                ))
            else:
                checks.append(AdapterEnvironmentCheck(
                    code="process_cwd_invalid",
                    level="error",
                    message=f"工作目录不存在: {cwd}",
                    detail=cwd,
                ))

        return AdapterEnvironmentTestResult(
            adapter_type="process",
            status=AdapterEnvironmentTestResult.summarize_status(checks),
            checks=checks,
        )

    @classmethod
    def get_config_schema(cls) -> dict:
        return {
            "command": {"type": "str", "required": True, "description": "要执行的命令"},
            "args": {"type": "list[str]", "required": False, "description": "命令参数"},
            "cwd": {"type": "str", "required": False, "description": "工作目录"},
            "env": {"type": "dict[str,str]", "required": False, "description": "额外环境变量"},
            "timeout_sec": {"type": "int", "required": False, "description": "超时秒数"},
            "grace_sec": {"type": "int", "required": False, "description": "SIGTERM 宽限秒数"},
        }
