from typing import Any, Dict, Optional, Sequence


def resolve_provider_config(
    provider: str,
    component_key: str,
    explicit_config: Optional[Dict[str, Any]] = None,
    config_name: Optional[str] = None,
) -> Dict[str, Any]:
    merged = {}
    if config_name:
        merged.update(
            _load_config_from_django(
                provider=provider,
                component_key=component_key,
                config_name=config_name,
            )
        )
    if explicit_config:
        merged.update({key: value for key, value in explicit_config.items() if value not in (None, "")})
    return merged


def require_fields(config: Dict[str, Any], fields: Sequence[str]) -> Optional[str]:
    for field in fields:
        value = config.get(field)
        if value in (None, ""):
            return field
    return None


def _load_config_from_django(provider: str, component_key: str, config_name: str) -> Dict[str, Any]:
    try:
        import django
        from django.apps import apps
    except Exception as exc:
        raise RuntimeError("当前环境不可用 Django，无法按 config_name 读取数据库配置") from exc

    if not apps.ready:
        try:
            django.setup()
        except Exception as exc:
            raise RuntimeError("Django 初始化失败，无法读取通信配置") from exc

    generic_model = apps.get_model("collector", "ComponentSystemParamConfig")
    if generic_model is not None:
        generic_record = (
            generic_model.objects.filter(
                component_key=component_key,
                config_name=config_name,
                is_enabled=True,
            )
            .only("params")
            .first()
        )
        if generic_record:
            data = generic_record.params or {}
            if not isinstance(data, dict):
                raise RuntimeError("组件系统参数配置格式错误，params 必须是 JSON 对象")
            return data

    model = apps.get_model("collector", "CommunicationChannelConfig")
    if model is None:
        raise RuntimeError("未找到组件参数配置模型")

    record = model.objects.filter(provider=provider, name=config_name, is_enabled=True).only("config").first()
    if not record:
        raise RuntimeError(
            f"未找到启用中的组件参数配置: component_key={component_key}, config_name={config_name}"
        )

    data = record.config or {}
    if not isinstance(data, dict):
        raise RuntimeError("通信配置格式错误，config 必须是 JSON 对象")
    return data
