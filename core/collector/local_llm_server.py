import os
import shlex
import socket
import subprocess
import threading
import time
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError


_START_LOCK = threading.Lock()
_STARTING_ENDPOINTS = set()


def _is_truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_local_endpoint(endpoint: str) -> bool:
    parsed = urlparse(str(endpoint or "").strip())
    host = (parsed.hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def _ping_endpoint(endpoint: str, timeout: float = 2.0):
    url = f"{str(endpoint or '').rstrip('/')}/api/tags"
    req = urllib_request.Request(url=url, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=timeout):
            return True, None
    except urllib_error.HTTPError as ex:
        detail = ex.read().decode("utf-8", errors="ignore")
        return False, f"HTTP {ex.code}: {detail or ex.reason}"
    except urllib_error.URLError as ex:
        return False, f"连接失败：{getattr(ex, 'reason', ex)}"
    except Exception as ex:
        return False, str(ex)


def _resolve_host_port(endpoint: str):
    parsed = urlparse(str(endpoint or "").strip())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11434
    return host, port


def _can_connect_port(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _start_ollama_serve(endpoint: str):
    command = str(getattr(settings, "LOCAL_LLM_OLLAMA_COMMAND", "ollama serve") or "ollama serve").strip()
    cmd = shlex.split(command)
    env = os.environ.copy()
    host, port = _resolve_host_port(endpoint)
    env["OLLAMA_HOST"] = f"{host}:{port}"
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )


def ensure_local_ollama_server(endpoint: str):
    """
    确保本地 endpoint 的 Ollama 服务可用。
    返回 (ok: bool, error: str|None)。
    """
    endpoint = str(endpoint or "").strip().rstrip("/")
    if not endpoint:
        return False, "endpoint 不能为空。"

    ok, error = _ping_endpoint(endpoint)
    if ok:
        return True, None

    if not _is_truthy(getattr(settings, "LOCAL_LLM_AUTO_START", True)):
        return False, error
    if not _is_local_endpoint(endpoint):
        return False, error

    with _START_LOCK:
        if endpoint not in _STARTING_ENDPOINTS:
            _STARTING_ENDPOINTS.add(endpoint)
            try:
                host, port = _resolve_host_port(endpoint)
                if not _can_connect_port(host, port):
                    _start_ollama_serve(endpoint)
            except FileNotFoundError:
                _STARTING_ENDPOINTS.discard(endpoint)
                return False, "未找到 ollama 命令，请先安装 Ollama。"
            except Exception as ex:
                _STARTING_ENDPOINTS.discard(endpoint)
                return False, f"自动启动 Ollama 失败：{ex}"

    timeout_seconds = float(getattr(settings, "LOCAL_LLM_AUTO_START_TIMEOUT_SECONDS", 20) or 20)
    deadline = time.time() + max(1.0, timeout_seconds)
    last_error = error
    while time.time() < deadline:
        ok, ping_error = _ping_endpoint(endpoint, timeout=2.0)
        if ok:
            with _START_LOCK:
                _STARTING_ENDPOINTS.discard(endpoint)
            return True, None
        last_error = ping_error or last_error
        time.sleep(0.5)

    with _START_LOCK:
        _STARTING_ENDPOINTS.discard(endpoint)
    return False, last_error or "Ollama 服务未就绪。"


def bootstrap_local_ollama_for_enabled_configs():
    if not _is_truthy(getattr(settings, "LOCAL_LLM_AUTO_START_ON_DJANGO_STARTUP", True)):
        return

    from .models import LocalLLMConfig

    try:
        endpoints = (
            LocalLLMConfig.objects.filter(
                is_enabled=True,
                runtime_backend=LocalLLMConfig.BACKEND_OLLAMA,
            )
            .values_list("endpoint", flat=True)
            .distinct()
        )
        for endpoint in endpoints:
            endpoint_value = str(endpoint or "").strip()
            if not endpoint_value:
                continue
            ensure_local_ollama_server(endpoint_value)
    except (OperationalError, ProgrammingError):
        # 应用初始迁移阶段忽略数据库未就绪问题
        return
