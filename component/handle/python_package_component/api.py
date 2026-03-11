import importlib.metadata
import subprocess
import sys
from typing import Any, Dict, List


def query_python_package(package_name: str) -> Dict[str, Any]:
    """查询 Python 包是否安装及基础元信息。"""
    normalized_name = (package_name or "").strip()
    if not normalized_name:
        return {"success": False, "error": "package_name 不能为空"}

    try:
        distribution = importlib.metadata.distribution(normalized_name)
    except importlib.metadata.PackageNotFoundError:
        return {
            "success": True,
            "data": {
                "package_name": normalized_name,
                "installed": False,
            },
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    metadata = distribution.metadata
    return {
        "success": True,
        "data": {
            "package_name": normalized_name,
            "installed": True,
            "version": distribution.version,
            "location": str(distribution.locate_file("")),
            "summary": metadata.get("Summary", ""),
            "home_page": metadata.get("Home-page", ""),
            "requires": list(distribution.requires or []),
        },
    }


def install_python_package(
    package_name: str,
    version: str = "",
    upgrade: bool = False,
    timeout_seconds: int = 300,
    use_sudo: bool = False,
    sudo_password: str = "",
) -> Dict[str, Any]:
    """安装 Python 包。"""
    normalized_name = (package_name or "").strip()
    if not normalized_name:
        return {"success": False, "error": "package_name 不能为空"}
    if timeout_seconds <= 0:
        return {"success": False, "error": "timeout_seconds 必须 > 0"}

    package_spec = normalized_name
    normalized_version = (version or "").strip()
    if normalized_version:
        package_spec = f"{normalized_name}=={normalized_version}"

    command: List[str] = [sys.executable, "-m", "pip", "install", package_spec]
    if upgrade:
        command.append("--upgrade")
    if use_sudo:
        command = ["sudo", "-S", "-H"] + command

    return _run_pip_command(
        command=command,
        action="install_python_package",
        package_name=normalized_name,
        timeout_seconds=timeout_seconds,
        use_sudo=use_sudo,
        sudo_password=sudo_password,
    )


def uninstall_python_package(
    package_name: str,
    timeout_seconds: int = 300,
    use_sudo: bool = False,
    sudo_password: str = "",
) -> Dict[str, Any]:
    """卸载 Python 包。"""
    normalized_name = (package_name or "").strip()
    if not normalized_name:
        return {"success": False, "error": "package_name 不能为空"}
    if timeout_seconds <= 0:
        return {"success": False, "error": "timeout_seconds 必须 > 0"}

    command: List[str] = [
        sys.executable,
        "-m",
        "pip",
        "uninstall",
        normalized_name,
        "-y",
    ]
    if use_sudo:
        command = ["sudo", "-S", "-H"] + command
    return _run_pip_command(
        command=command,
        action="uninstall_python_package",
        package_name=normalized_name,
        timeout_seconds=timeout_seconds,
        use_sudo=use_sudo,
        sudo_password=sudo_password,
    )


def _run_pip_command(
    command: List[str],
    action: str,
    package_name: str,
    timeout_seconds: int,
    use_sudo: bool = False,
    sudo_password: str = "",
) -> Dict[str, Any]:
    if use_sudo and not sudo_password:
        return {"success": False, "error": "use_sudo=true 时必须提供 sudo_password"}

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            input=(f"{sudo_password}\n" if use_sudo else None),
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"{action} 执行超时（>{timeout_seconds}s）",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    stdout_text = (completed.stdout or "").strip()
    stderr_text = (completed.stderr or "").strip()
    if completed.returncode != 0:
        return {
            "success": False,
            "error": stderr_text or stdout_text or "pip 命令执行失败",
            "data": {
                "action": action,
                "package_name": package_name,
                "command": command,
                "return_code": completed.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text,
            },
        }

    return {
        "success": True,
        "data": {
            "action": action,
            "package_name": package_name,
            "command": command,
            "return_code": completed.returncode,
            "stdout": stdout_text,
            "stderr": stderr_text,
        },
    }
