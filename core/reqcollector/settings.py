import os
from pathlib import Path

from reqcollector.path_bootstrap import ENV_PROJECT_ROOT_KEY, resolve_project_root

CORE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = resolve_project_root(os.getenv(ENV_PROJECT_ROOT_KEY, ""))
# 兼容 Django 默认命名，保留 BASE_DIR 指向 core 目录。
BASE_DIR = CORE_DIR

SECRET_KEY = "django-insecure-change-me-in-production"
DEBUG = True
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "collector.apps.CollectorConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "reqcollector.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "reqcollector.wsgi.application"
ASGI_APPLICATION = "reqcollector.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# 媒体文件配置
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "session_list"
LOGOUT_REDIRECT_URL = "login"

# 大模型配置
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")
try:
    CHAT_CONTEXT_MESSAGE_LIMIT = int(os.getenv("CHAT_CONTEXT_MESSAGE_LIMIT", "50"))
except ValueError:
    CHAT_CONTEXT_MESSAGE_LIMIT = 50
try:
    CHAT_REPLY_EMIT_CHUNK_SIZE = int(os.getenv("CHAT_REPLY_EMIT_CHUNK_SIZE", "120"))
except ValueError:
    CHAT_REPLY_EMIT_CHUNK_SIZE = 120
try:
    CHAT_REPLY_EMIT_INTERVAL_SECONDS = float(os.getenv("CHAT_REPLY_EMIT_INTERVAL_SECONDS", "1"))
except ValueError:
    CHAT_REPLY_EMIT_INTERVAL_SECONDS = 1.0
try:
    CHAT_REPLY_TASK_TIMEOUT_SECONDS = float(os.getenv("CHAT_REPLY_TASK_TIMEOUT_SECONDS", "180"))
except ValueError:
    CHAT_REPLY_TASK_TIMEOUT_SECONDS = 180.0
try:
    CHAT_REPLY_TASK_HEARTBEAT_INTERVAL_SECONDS = float(
        os.getenv("CHAT_REPLY_TASK_HEARTBEAT_INTERVAL_SECONDS", "1.5")
    )
except ValueError:
    CHAT_REPLY_TASK_HEARTBEAT_INTERVAL_SECONDS = 1.5
try:
    CHAT_REPLY_TASK_STUCK_GRACE_SECONDS = float(os.getenv("CHAT_REPLY_TASK_STUCK_GRACE_SECONDS", "20"))
except ValueError:
    CHAT_REPLY_TASK_STUCK_GRACE_SECONDS = 20.0
try:
    CHAT_REPLY_TASK_TRACE_MAX_EVENTS = int(os.getenv("CHAT_REPLY_TASK_TRACE_MAX_EVENTS", "500"))
except ValueError:
    CHAT_REPLY_TASK_TRACE_MAX_EVENTS = 500
COMPANION_CAPABILITY_SEARCH_MODE = str(os.getenv("COMPANION_CAPABILITY_SEARCH_MODE", "hybrid")).strip().lower() or "hybrid"
if COMPANION_CAPABILITY_SEARCH_MODE not in {"traditional", "vector", "hybrid"}:
    COMPANION_CAPABILITY_SEARCH_MODE = "hybrid"
COMPANION_MINDFORGE_STRATEGY = str(os.getenv("COMPANION_MINDFORGE_STRATEGY", "auto")).strip().lower() or "auto"
if COMPANION_MINDFORGE_STRATEGY not in {"auto", "react", "cot", "plan_execute", "reflexion"}:
    COMPANION_MINDFORGE_STRATEGY = "auto"

# 本地模型服务自动启动配置
LOCAL_LLM_AUTO_START = str(os.getenv("LOCAL_LLM_AUTO_START", "1")).strip().lower() in {"1", "true", "yes", "on"}
LOCAL_LLM_AUTO_START_ON_DJANGO_STARTUP = str(
    os.getenv("LOCAL_LLM_AUTO_START_ON_DJANGO_STARTUP", "1")
).strip().lower() in {"1", "true", "yes", "on"}
try:
    LOCAL_LLM_AUTO_START_TIMEOUT_SECONDS = float(os.getenv("LOCAL_LLM_AUTO_START_TIMEOUT_SECONDS", "20"))
except ValueError:
    LOCAL_LLM_AUTO_START_TIMEOUT_SECONDS = 20.0
LOCAL_LLM_OLLAMA_COMMAND = str(os.getenv("LOCAL_LLM_OLLAMA_COMMAND", "ollama serve")).strip() or "ollama serve"
