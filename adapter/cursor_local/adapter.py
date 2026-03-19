from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from adapter.base import BaseAdapter
from adapter.cursor_local.parser import is_unknown_session_error, parse_cursor_stream_json
from adapter.types import (
    AdapterEnvironmentCheck,
    AdapterEnvironmentTestResult,
    AdapterExecutionContext,
    AdapterExecutionResult,
)


class CursorLocalAdapter(BaseAdapter):
    adapter_type = "cursor_local"
    label = "Cursor CLI (本地)"
    config_doc = (
        "command (str, 可选): Cursor CLI 命令，默认 agent\n"
        "cwd (str, 可选): 工作目录\n"
        "model (str, 可选): 模型，默认 auto\n"
        "mode (str, 可选): plan / ask\n"
        "extra_args (list[str] | str, 可选): 额外参数\n"
        "instructions_file_path (str, 可选): 指令文件路径\n"
        "session_id (str, 可选): 续跑会话 ID\n"
        "session_cwd (str, 可选): 上次会话 cwd（用于校验）\n"
        "workspace_id (str, 可选): 上层 workspace 标识\n"
        "env (dict[str,str], 可选): 额外环境变量\n"
        "timeout_sec (int, 可选): 超时秒数，0=不限\n"
        "hello_probe (bool, 可选): test_environment 时是否执行 hello 探针\n"
    )

    def execute(self, context: AdapterExecutionContext) -> AdapterExecutionResult:
        config = context.config or {}
        command = str(config.get("command", "agent") or "agent").strip()
        cwd = str(config.get("cwd", "") or context.cwd or "").strip() or os.getcwd()
        model = str(config.get("model", "auto") or "auto").strip()
        mode = self._normalize_mode(config.get("mode"))
        timeout_sec = int(config.get("timeout_sec", 0) or context.timeout_sec or 0)
        timeout = timeout_sec if timeout_sec > 0 else None
        extra_args = self._normalize_extra_args(config.get("extra_args"))
        if not self._has_trust_bypass(extra_args):
            extra_args = ["--yolo", *extra_args]

        env = {**os.environ, **(context.env or {})}
        for key, value in (config.get("env") or {}).items():
            if isinstance(key, str) and isinstance(value, str):
                env[key] = value

        prompt = self._build_prompt(
            prompt=context.prompt or "",
            instructions_file_path=str(config.get("instructions_file_path", "") or "").strip(),
        )

        configured_session_id = str(config.get("session_id", "") or "").strip()
        configured_session_cwd = str(config.get("session_cwd", "") or "").strip()
        resume_session_id: str | None = None
        resume_skipped_reason: str | None = None
        if configured_session_id:
            if configured_session_cwd and os.path.abspath(configured_session_cwd) != os.path.abspath(cwd):
                resume_skipped_reason = "session cwd mismatch"
            else:
                resume_session_id = configured_session_id

        first_run = self._run_once(
            command=command,
            cwd=cwd,
            model=model,
            mode=mode,
            extra_args=extra_args,
            prompt=prompt,
            timeout=timeout,
            env=env,
            resume_session_id=resume_session_id,
        )
        parsed = parse_cursor_stream_json(first_run.stdout)

        if (
            resume_session_id
            and first_run.returncode != 0
            and is_unknown_session_error(first_run.stdout, first_run.stderr)
        ):
            retry_run = self._run_once(
                command=command,
                cwd=cwd,
                model=model,
                mode=mode,
                extra_args=extra_args,
                prompt=prompt,
                timeout=timeout,
                env=env,
                resume_session_id=None,
            )
            parsed_retry = parse_cursor_stream_json(retry_run.stdout)
            return self._build_result(
                proc=retry_run,
                parsed=parsed_retry,
                cwd=cwd,
                workspace_id=str(config.get("workspace_id", "") or "").strip() or None,
                resumed=False,
                resume_retried=True,
                resume_skipped_reason=resume_skipped_reason,
            )

        return self._build_result(
            proc=first_run,
            parsed=parsed,
            cwd=cwd,
            workspace_id=str(config.get("workspace_id", "") or "").strip() or None,
            resumed=bool(resume_session_id),
            resume_retried=False,
            resume_skipped_reason=resume_skipped_reason,
        )

    def _run_once(
        self,
        *,
        command: str,
        cwd: str,
        model: str,
        mode: str | None,
        extra_args: list[str],
        prompt: str,
        timeout: int | None,
        env: dict[str, str],
        resume_session_id: str | None,
    ) -> subprocess.CompletedProcess[str]:
        args = ["-p", "--output-format", "stream-json", "--workspace", cwd]
        if resume_session_id:
            args.extend(["--resume", resume_session_id])
        if model:
            args.extend(["--model", model])
        if mode:
            args.extend(["--mode", mode])
        args.extend(extra_args)

        try:
            return subprocess.run(
                [command, *args],
                cwd=cwd,
                env=env,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                args=[command, *args],
                returncode=-1,
                stdout="",
                stderr=f"Timed out after {timeout or 0}s",
            )
        except FileNotFoundError:
            return subprocess.CompletedProcess(
                args=[command, *args],
                returncode=127,
                stdout="",
                stderr=f"命令未找到: {command}",
            )
        except Exception as exc:  # noqa: BLE001
            return subprocess.CompletedProcess(
                args=[command, *args],
                returncode=1,
                stdout="",
                stderr=f"执行异常: {exc}",
            )

    def _build_result(
        self,
        *,
        proc: subprocess.CompletedProcess[str],
        parsed: dict[str, Any],
        cwd: str,
        workspace_id: str | None,
        resumed: bool,
        resume_retried: bool,
        resume_skipped_reason: str | None,
    ) -> AdapterExecutionResult:
        summary = str(parsed.get("summary", "") or "").strip()
        error_from_stream = str(parsed.get("error_message", "") or "").strip()
        error_message: str | None = None
        if proc.returncode != 0:
            first_stderr = next((line.strip() for line in proc.stderr.splitlines() if line.strip()), "")
            error_message = error_from_stream or first_stderr or f"进程退出码 {proc.returncode}"

        session_id = parsed.get("session_id")
        usage = parsed.get("usage") if isinstance(parsed.get("usage"), dict) else {}
        result_json: dict[str, Any] = {
            "session_id": session_id,
            "session_params": {
                "session_id": session_id,
                "cwd": cwd,
                "workspace_id": workspace_id,
            },
            "usage": usage,
            "cost_usd": parsed.get("cost_usd"),
            "summary": summary,
            "resumed": resumed,
            "resume_retried": resume_retried,
            "resume_skipped_reason": resume_skipped_reason,
        }
        return AdapterExecutionResult(
            exit_code=proc.returncode,
            timed_out=proc.returncode == -1 and "Timed out" in (proc.stderr or ""),
            error_message=error_message,
            stdout=proc.stdout,
            stderr=proc.stderr,
            result_json=result_json,
        )

    def test_environment(self, config: dict) -> AdapterEnvironmentTestResult:
        checks: list[AdapterEnvironmentCheck] = []
        command = str(config.get("command", "agent") or "agent").strip()
        cwd = str(config.get("cwd", "") or "").strip()

        if command:
            checks.append(
                AdapterEnvironmentCheck(
                    code="cursor_command_present",
                    level="info",
                    message=f"配置的命令: {command}",
                )
            )
        else:
            checks.append(
                AdapterEnvironmentCheck(
                    code="cursor_command_missing",
                    level="error",
                    message="cursor_local adapter 需要 command。",
                    hint="将 command 设置为 agent 或可执行绝对路径。",
                )
            )

        if command and shutil.which(command):
            checks.append(
                AdapterEnvironmentCheck(
                    code="cursor_command_resolvable",
                    level="info",
                    message=f"命令可执行: {command}",
                )
            )
        else:
            checks.append(
                AdapterEnvironmentCheck(
                    code="cursor_command_unresolvable",
                    level="error",
                    message=f"命令不可执行或未在 PATH 中找到: {command}",
                    detail=command,
                )
            )

        if cwd:
            if os.path.isdir(cwd):
                checks.append(
                    AdapterEnvironmentCheck(
                        code="cursor_cwd_valid",
                        level="info",
                        message=f"工作目录有效: {cwd}",
                    )
                )
            else:
                checks.append(
                    AdapterEnvironmentCheck(
                        code="cursor_cwd_invalid",
                        level="error",
                        message=f"工作目录不存在: {cwd}",
                        detail=cwd,
                    )
                )

        if bool(config.get("hello_probe")) and command and shutil.which(command):
            probe = subprocess.run(
                [
                    command,
                    "-p",
                    "--mode",
                    "ask",
                    "--output-format",
                    "json",
                    "--yolo",
                    "Respond with hello.",
                ],
                capture_output=True,
                text=True,
                timeout=45,
            )
            if probe.returncode == 0:
                checks.append(
                    AdapterEnvironmentCheck(
                        code="cursor_hello_probe_ok",
                        level="info",
                        message="hello probe 成功。",
                    )
                )
            else:
                checks.append(
                    AdapterEnvironmentCheck(
                        code="cursor_hello_probe_failed",
                        level="warn",
                        message="hello probe 失败。",
                        detail=(probe.stderr or probe.stdout or "").strip(),
                        hint="确认 Cursor CLI 已登录并可执行。",
                    )
                )

        return AdapterEnvironmentTestResult(
            adapter_type=self.adapter_type,
            status=AdapterEnvironmentTestResult.summarize_status(checks),
            checks=checks,
        )

    @classmethod
    def get_config_schema(cls) -> dict:
        return {
            "command": {"type": "str", "required": False, "description": "Cursor CLI 命令，默认 agent"},
            "cwd": {"type": "str", "required": False, "description": "工作目录"},
            "model": {"type": "str", "required": False, "description": "模型名称，默认 auto"},
            "mode": {"type": "str", "required": False, "description": "plan 或 ask"},
            "extra_args": {"type": "list[str]", "required": False, "description": "额外 CLI 参数"},
            "instructions_file_path": {
                "type": "str",
                "required": False,
                "description": "指令文件路径，内容会拼接到 prompt 前",
            },
            "session_id": {"type": "str", "required": False, "description": "用于 --resume 的会话 ID"},
            "session_cwd": {"type": "str", "required": False, "description": "上次会话 cwd"},
            "workspace_id": {"type": "str", "required": False, "description": "上层 workspace 标识"},
            "env": {"type": "dict[str,str]", "required": False, "description": "额外环境变量"},
            "timeout_sec": {"type": "int", "required": False, "description": "超时秒数"},
            "hello_probe": {"type": "bool", "required": False, "description": "环境检测时执行 hello 探针"},
        }

    @staticmethod
    def _normalize_extra_args(value: Any) -> list[str]:
        if isinstance(value, str):
            return [item for item in value.split(" ") if item]
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return []

    @staticmethod
    def _normalize_mode(value: Any) -> str | None:
        mode = str(value or "").strip().lower()
        if mode in {"plan", "ask"}:
            return mode
        return None

    @staticmethod
    def _has_trust_bypass(extra_args: list[str]) -> bool:
        trust_flags = {"--trust", "--yolo", "-f"}
        return any(arg in trust_flags for arg in extra_args)

    @staticmethod
    def _build_prompt(prompt: str, instructions_file_path: str) -> str:
        if not instructions_file_path:
            return prompt
        try:
            with open(instructions_file_path, "r", encoding="utf-8") as f:
                instructions = f.read()
        except OSError:
            return prompt
        instructions_dir = os.path.dirname(instructions_file_path) or "."
        suffix = (
            f"The above agent instructions were loaded from {instructions_file_path}. "
            f"Resolve any relative file references from {instructions_dir}."
        )
        return f"{instructions}\n\n{suffix}\n\n{prompt}".strip()
