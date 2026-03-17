from django.apps import AppConfig
import os
import sys


class CollectorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "collector"

    def ready(self):
        command = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
        skip_commands = {
            "makemigrations",
            "migrate",
            "collectstatic",
            "shell",
            "dbshell",
            "test",
        }
        if command in skip_commands:
            return
        # Django runserver 自动重载父进程不执行，仅在实际服务进程执行。
        if command in {"runserver", "runserver_plus"} and os.environ.get("RUN_MAIN") not in {"true", "1"}:
            return

        from .orchestration.capability_search import preload_capability_index, refresh_capability_index

        try:
            refresh_capability_index()
        except Exception:
            # 刷新失败时退化为预加载，避免启动阶段因索引刷新异常阻断服务。
            preload_capability_index()
        from .views import recover_interrupted_chat_reply_tasks_once

        recover_interrupted_chat_reply_tasks_once()
        if command in {"runserver", "runserver_plus"}:
            from .local_llm_server import bootstrap_local_ollama_for_enabled_configs

            bootstrap_local_ollama_for_enabled_configs()
