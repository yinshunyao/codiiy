import importlib
import importlib.metadata
import inspect
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ComponentCallTool:
    """component 通用调用工具：支持信息查询与字符串路径调用。"""

    def __init__(self, auto_install: Optional[bool] = None):
        self.auto_install = self._resolve_auto_install(auto_install)
        self.tool_dir = Path(__file__).resolve().parent
        self.repo_root = self.tool_dir.parent.parent
        self.component_dir = self.repo_root / "component"
        self._ensure_repo_path()

    def control_info(self) -> Dict[str, Any]:
        """查询 component 整体信息（来自各目录 README.json）。"""
        try:
            if not self.component_dir.exists():
                return {"success": False, "error": f"component 目录不存在: {self.component_dir}"}

            readmes = sorted(self.component_dir.rglob("README.json"))
            modules: List[Dict[str, Any]] = []
            all_functions: List[Dict[str, Any]] = []
            for path in readmes:
                module_data = self._read_module_readme(path)
                modules.append(module_data)
                for func in module_data.get("functions", []):
                    if isinstance(func, dict):
                        all_functions.append(func)

            return {
                "success": True,
                "data": {
                    "component_root": str(self.component_dir),
                    "module_count": len(modules),
                    "function_count": len(all_functions),
                    "modules": modules,
                    "functions": all_functions,
                },
            }
        except Exception as exc:
            logger.exception("control_info failed")
            return {"success": False, "error": str(exc)}

    def control_call(
        self,
        function_path: str,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """通过字符串路径调用 component 函数。"""
        try:
            permission_result = self._check_system_permissions(function_path=function_path)
            if not permission_result["success"]:
                return permission_result

            ensure_result = self.ensure_dependencies(function_path=function_path)
            if not ensure_result["success"]:
                return ensure_result

            result = self._invoke_control_function(function_path=function_path, kwargs=kwargs or {})
            return {
                "success": True,
                "data": {
                    "function_path": function_path,
                    "result": result,
                },
            }
        except Exception as exc:
            logger.exception("control_call failed")
            return {"success": False, "error": str(exc)}

    def _check_system_permissions(self, function_path: str) -> Dict[str, Any]:
        """
        按组件声明校验必需系统权限（required=true）。

        仅在 Django 权限存储可用时执行强拦截；不可用时按降级策略放行。
        """
        component_key = self._resolve_component_key(function_path=function_path)
        if not component_key:
            return {"success": True, "data": {"permission_checked": False, "reason": "function_not_managed"}}

        required_permission_keys = self._load_component_required_permission_keys(component_key=component_key)
        if not required_permission_keys:
            return {"success": True, "data": {"permission_checked": False, "reason": "no_required_permissions"}}

        grant_model = self._load_permission_grant_model()
        if grant_model is None:
            return {
                "success": True,
                "data": {
                    "permission_checked": False,
                    "reason": "permission_storage_unavailable",
                    "component_key": component_key,
                },
            }

        granted_keys = self._query_granted_permission_keys(
            grant_model=grant_model,
            component_key=component_key,
            permission_keys=required_permission_keys,
        )
        if granted_keys is None:
            return {
                "success": True,
                "data": {
                    "permission_checked": False,
                    "reason": "permission_storage_query_failed",
                    "component_key": component_key,
                },
            }

        missing_keys = [key for key in required_permission_keys if key not in granted_keys]
        if missing_keys:
            return {
                "success": False,
                "error": f"组件缺少必需系统权限确认: {component_key}",
                "data": {
                    "component_key": component_key,
                    "missing_permissions": missing_keys,
                },
            }

        return {
            "success": True,
            "data": {
                "permission_checked": True,
                "component_key": component_key,
                "required_permissions": required_permission_keys,
            },
        }

    # 兼容旧方法名
    def call_control_function(
        self,
        function_path: str,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.control_call(function_path=function_path, kwargs=kwargs)

    def ensure_dependencies(self, function_path: str) -> Dict[str, Any]:
        """按函数所属组件检查并确保依赖已安装。"""
        try:
            requirements_paths = self._resolve_requirements_paths(function_path=function_path)
            if not requirements_paths:
                return {
                    "success": True,
                    "data": {
                        "installed": True,
                        "missing": [],
                        "requirements_files": [],
                        "reason": "no_component_requirements",
                    },
                }

            requirements = self._read_requirements_from_paths(requirements_paths=requirements_paths)
            missing = [req for req in requirements if not self._is_requirement_installed(req)]
            if not missing:
                return {
                    "success": True,
                    "data": {
                        "installed": True,
                        "missing": [],
                        "requirements_files": [str(p) for p in requirements_paths],
                    },
                }

            if not self.auto_install:
                return {
                    "success": False,
                    "error": (
                        f"缺少依赖: {missing}，当前策略禁止运行时自动安装（auto_install=False）。"
                        "请优先在虚拟环境中预先安装依赖，并避免使用 sudo 直接运行 Django。"
                    ),
                }

            logger.info("Installing missing dependencies: %s", missing)
            for requirements_path in requirements_paths:
                cmd = [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)]
                completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if completed.returncode != 0:
                    return {
                        "success": False,
                        "error": f"依赖安装失败: {completed.stderr.strip() or completed.stdout.strip()}",
                    }

            still_missing = [req for req in requirements if not self._is_requirement_installed(req)]
            if still_missing:
                return {"success": False, "error": f"依赖安装后仍缺失: {still_missing}"}

            return {
                "success": True,
                "data": {
                    "installed": True,
                    "missing": missing,
                    "installed_now": True,
                    "requirements_files": [str(p) for p in requirements_paths],
                },
            }
        except Exception as exc:
            logger.exception("ensure_dependencies failed")
            return {"success": False, "error": str(exc)}

    def get_component_enabled(self, component_key: str) -> Dict[str, Any]:
        """查询组件是否启用。"""
        try:
            from component import get_component_enabled

            enabled = bool(get_component_enabled(component_key))
            return {"success": True, "data": {"component_key": component_key, "enabled": enabled}}
        except Exception as exc:
            logger.exception("get_component_enabled failed")
            return {"success": False, "error": str(exc)}

    def set_component_enabled(self, component_key: str, enabled: bool) -> Dict[str, Any]:
        """设置组件启停状态。"""
        try:
            from component import set_component_enabled

            set_component_enabled(component_key, bool(enabled))
            return {"success": True, "data": {"component_key": component_key, "enabled": bool(enabled)}}
        except Exception as exc:
            logger.exception("set_component_enabled failed")
            return {"success": False, "error": str(exc)}

    def _read_module_readme(self, path: Path) -> Dict[str, Any]:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        if not isinstance(data, dict):
            return {"readme_path": str(path), "error": "README.json 不是 JSON 对象"}

        data["readme_path"] = str(path)
        return data

    def _read_requirements_from_paths(self, requirements_paths: List[Path]) -> List[str]:
        requirements: List[str] = []
        for requirements_path in requirements_paths:
            for raw in requirements_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                requirements.append(line)
        # 去重并保持顺序，避免同一依赖重复检查。
        deduped: List[str] = []
        seen = set()
        for req in requirements:
            if req in seen:
                continue
            seen.add(req)
            deduped.append(req)
        return deduped

    def _resolve_requirements_paths(self, function_path: str) -> List[Path]:
        component_dir = self._resolve_component_dir(function_path=function_path)
        if not component_dir:
            return []
        requirements_path = component_dir / "requirements.txt"
        if not requirements_path.exists():
            return []
        return [requirements_path]

    def _resolve_component_dir(self, function_path: str) -> Optional[Path]:
        component_index = self._read_component_index()
        function_to_component = component_index.get("function_to_component", {})
        components = component_index.get("components", {})

        if not isinstance(function_to_component, dict):
            return None
        if not isinstance(components, dict):
            return None

        component_key = function_to_component.get(function_path)
        if not isinstance(component_key, str):
            return None

        component_meta = components.get(component_key, {})
        if not isinstance(component_meta, dict):
            return None
        component_dir_raw = component_meta.get("component_dir")
        if not isinstance(component_dir_raw, str) or not component_dir_raw.strip():
            return None

        component_dir = self.repo_root / component_dir_raw
        if not component_dir.exists():
            raise FileNotFoundError(f"组件目录不存在: {component_dir}")
        return component_dir

    def _resolve_component_key(self, function_path: str) -> str:
        component_index = self._read_component_index()
        function_to_component = component_index.get("function_to_component", {})
        if not isinstance(function_to_component, dict):
            return ""
        component_key = function_to_component.get(function_path)
        if not isinstance(component_key, str):
            return ""
        return component_key.strip()

    def _load_component_required_permission_keys(self, component_key: str) -> List[str]:
        module_name = str(component_key or "").split(".", 1)[0].strip()
        if not module_name:
            return []
        readme_path = self.component_dir / module_name / "README.json"
        if not readme_path.exists():
            return []

        try:
            payload = json.loads(readme_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []

        components = payload.get("components", [])
        if not isinstance(components, list):
            return []

        target_item = None
        for item in components:
            if not isinstance(item, dict):
                continue
            if str(item.get("component_key") or "").strip() == component_key:
                target_item = item
                break
        if not isinstance(target_item, dict):
            return []

        permission_schema = target_item.get("system_permission_schema")
        if not isinstance(permission_schema, dict):
            return []
        if not bool(permission_schema.get("enabled")):
            return []

        permissions = permission_schema.get("permissions", [])
        if not isinstance(permissions, list):
            return []

        required_keys: List[str] = []
        for item in permissions:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            if not bool(item.get("required")):
                continue
            if key in required_keys:
                continue
            required_keys.append(key)
        return required_keys

    @staticmethod
    def _load_permission_grant_model():
        try:
            from django.apps import apps
            from django.conf import settings
        except Exception:
            return None

        try:
            if not settings.configured:
                return None
            if not apps.ready:
                return None
            return apps.get_model("collector", "ComponentSystemPermissionGrant")
        except Exception:
            return None

    @staticmethod
    def _query_granted_permission_keys(
        grant_model,
        component_key: str,
        permission_keys: List[str],
    ) -> Optional[Set[str]]:
        try:
            records = grant_model.objects.filter(
                component_key=component_key,
                permission_key__in=permission_keys,
            ).only("permission_key", "is_granted")
            return {
                str(item.permission_key).strip()
                for item in records
                if bool(getattr(item, "is_granted", False))
            }
        except Exception:
            return None

    def _read_component_index(self) -> Dict[str, Any]:
        index_path = self.component_dir / "component_index.json"
        if not index_path.exists():
            raise FileNotFoundError(f"component_index.json 不存在: {index_path}")
        data = json.loads(index_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("component_index.json 不是 JSON 对象")
        return data

    def _is_requirement_installed(self, requirement_line: str) -> bool:
        package_name = self._extract_package_name(requirement_line)
        if not package_name:
            return True

        try:
            importlib.metadata.version(package_name)
            return True
        except importlib.metadata.PackageNotFoundError:
            pass

        import_name = self._get_import_name_map().get(
            package_name.lower(),
            package_name.replace("-", "_"),
        )
        try:
            importlib.import_module(import_name)
            return True
        except Exception:
            return False

    @staticmethod
    def _extract_package_name(requirement_line: str) -> str:
        line = requirement_line.split(";", 1)[0].strip()
        line = line.split("[", 1)[0].strip()
        match = re.match(r"^([A-Za-z0-9_.-]+)", line)
        return match.group(1) if match else ""

    def _get_import_name_map(self) -> Dict[str, str]:
        component_readme = self.component_dir / "README.json"
        if not component_readme.exists():
            return {}
        try:
            data = json.loads(component_readme.read_text(encoding="utf-8"))
            tool_rules = data.get("tool_rules", {}) if isinstance(data, dict) else {}
            raw_map = tool_rules.get("dependency_import_name_map", {})
            if not isinstance(raw_map, dict):
                return {}
            mapped: Dict[str, str] = {}
            for k, v in raw_map.items():
                if isinstance(k, str) and isinstance(v, str):
                    mapped[k.lower()] = v
            return mapped
        except Exception:
            return {}

    def _ensure_repo_path(self) -> None:
        repo_path = str(self.repo_root)
        if repo_path not in sys.path:
            sys.path.insert(0, repo_path)

    @staticmethod
    def _resolve_auto_install(auto_install: Optional[bool]) -> bool:
        if auto_install is not None:
            return bool(auto_install)
        env_value = str(os.getenv("COMPONENT_AUTO_INSTALL", "")).strip().lower()
        return env_value in {"1", "true", "yes", "on"}

    def _invoke_control_function(self, function_path: str, kwargs: Dict[str, Any]) -> Any:
        from component import resolve_function

        func = resolve_function(function_path=function_path)
        safe_kwargs, dropped_keys = self._sanitize_kwargs_for_function(func=func, raw_kwargs=kwargs)
        if dropped_keys:
            logger.warning(
                "过滤不匹配参数: function=%s, dropped=%s",
                function_path,
                dropped_keys,
            )
        return func(**safe_kwargs)

    @staticmethod
    def _sanitize_kwargs_for_function(func, raw_kwargs: Optional[Dict[str, Any]]) -> tuple[Dict[str, Any], List[str]]:
        kwargs = raw_kwargs or {}
        if not isinstance(kwargs, dict):
            raise TypeError("kwargs 必须是 dict")

        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            # 无法解析签名时保持原样，避免误伤。
            return dict(kwargs), []

        parameters = signature.parameters
        accepts_var_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
        )
        if accepts_var_kwargs:
            return dict(kwargs), []

        allowed_keys = {
            name
            for name, parameter in parameters.items()
            if parameter.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
        }
        safe_kwargs: Dict[str, Any] = {}
        dropped_keys: List[str] = []
        for key, value in kwargs.items():
            if key in allowed_keys:
                safe_kwargs[key] = value
            else:
                dropped_keys.append(str(key))
        return safe_kwargs, dropped_keys

# 兼容旧类名，避免已有调用报错
ControlCallTool = ComponentCallTool
ScreenObserveTool = ComponentCallTool
