import os
import mimetypes
import re
from pathlib import Path
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError



class LLMProvider(models.Model):
    """大模型提供商"""
    name = models.CharField(max_length=100, unique=True, verbose_name="厂商名称")
    api_key_env = models.CharField(max_length=100, blank=True, verbose_name="API Key 环境变量名")

    class Meta:
        verbose_name = "大模型厂商"
        verbose_name_plural = "大模型厂商"

    def __str__(self):
        return self.name


class LLMModel(models.Model):
    """大模型"""
    provider = models.ForeignKey(LLMProvider, on_delete=models.CASCADE, related_name="models", verbose_name="厂商")
    name = models.CharField(max_length=100, verbose_name="模型名称")
    model_id = models.CharField(max_length=100, unique=True, verbose_name="模型 ID")
    is_default = models.BooleanField(default=False, verbose_name="是否默认")

    class Meta:
        verbose_name = "大模型"
        verbose_name_plural = "大模型"
        ordering = ["provider", "-is_default", "name"]

    def __str__(self):
        return f"{self.provider.name} - {self.name}"


class LLMApiConfig(models.Model):
    """大模型 API 配置。"""

    name = models.CharField(max_length=100, verbose_name="配置名称")
    provider_name = models.CharField(max_length=100, verbose_name="厂商名称")
    base_url = models.CharField(max_length=300, blank=True, verbose_name="API Base URL")
    api_key = models.CharField(max_length=300, blank=True, verbose_name="API Key")
    default_model_id = models.CharField(max_length=120, blank=True, verbose_name="默认模型 ID")
    is_enabled = models.BooleanField(default=True, verbose_name="是否启用")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="llm_api_configs",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "大模型 API 配置"
        verbose_name_plural = "大模型 API 配置"
        ordering = ["-updated_at", "name"]
        constraints = [
            models.UniqueConstraint(fields=["created_by", "name"], name="uniq_user_llm_api_config_name"),
        ]

    def __str__(self):
        return f"{self.provider_name} - {self.name}"


class LocalLLMConfig(models.Model):
    """本地大模型配置（支持 Ollama / llama-cpp-python）。"""

    BACKEND_OLLAMA = "ollama"
    BACKEND_LLAMA_CPP = "llama_cpp"
    BACKEND_CHOICES = [
        (BACKEND_OLLAMA, "Ollama 服务"),
        (BACKEND_LLAMA_CPP, "Python 组件（llama-cpp-python）"),
    ]

    name = models.CharField(max_length=100, verbose_name="配置名称")
    runtime_backend = models.CharField(
        max_length=32,
        choices=BACKEND_CHOICES,
        default=BACKEND_OLLAMA,
        verbose_name="本地模型实现模式",
    )
    endpoint = models.CharField(
        max_length=300,
        default="http://127.0.0.1:11434",
        blank=True,
        verbose_name="Ollama 地址",
    )
    model_name = models.CharField(max_length=120, verbose_name="模型名称")
    keep_alive = models.CharField(max_length=32, default="5m", verbose_name="keep_alive")
    model_file_path = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="llama-cpp 模型文件路径",
        help_text="仅 Python 组件模式使用，如 /data/models/qwen2.5-7b-instruct.gguf",
    )
    llama_cpp_n_ctx = models.PositiveIntegerField(default=4096, verbose_name="llama-cpp 上下文窗口")
    is_enabled = models.BooleanField(default=True, verbose_name="是否启用")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="local_llm_configs",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "本地大模型配置"
        verbose_name_plural = "本地大模型配置"
        ordering = ["-updated_at", "name"]
        constraints = [
            models.UniqueConstraint(fields=["created_by", "name"], name="uniq_user_local_llm_config_name"),
        ]

    def __str__(self):
        return self.name


class LocalLLMRuntimeTask(models.Model):
    """本地模型运行任务（异步）。"""

    ACTION_ACTIVATE = "activate"
    ACTION_DEACTIVATE = "deactivate"
    ACTION_CHOICES = [
        (ACTION_ACTIVATE, "激活模型"),
        (ACTION_DEACTIVATE, "取消激活"),
    ]

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_INTERRUPTED = "interrupted"
    STATUS_CHOICES = [
        (STATUS_PENDING, "等待中"),
        (STATUS_RUNNING, "执行中"),
        (STATUS_SUCCESS, "成功"),
        (STATUS_FAILED, "失败"),
        (STATUS_INTERRUPTED, "中断"),
    ]

    STAGE_QUEUED = "queued"
    STAGE_PULLING = "pulling"
    STAGE_WARMING = "warming"
    STAGE_UNLOADING = "unloading"
    STAGE_COMPLETED = "completed"
    STAGE_CHOICES = [
        (STAGE_QUEUED, "排队中"),
        (STAGE_PULLING, "拉取模型"),
        (STAGE_WARMING, "加载模型"),
        (STAGE_UNLOADING, "卸载模型"),
        (STAGE_COMPLETED, "完成"),
    ]

    config = models.ForeignKey(
        LocalLLMConfig,
        on_delete=models.CASCADE,
        related_name="runtime_tasks",
        verbose_name="本地模型配置",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="local_llm_runtime_tasks",
        verbose_name="创建人",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name="任务动作")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="任务状态",
    )
    stage = models.CharField(
        max_length=20,
        choices=STAGE_CHOICES,
        default=STAGE_QUEUED,
        verbose_name="任务阶段",
    )
    detail_message = models.TextField(blank=True, verbose_name="状态说明")
    error_message = models.TextField(blank=True, verbose_name="错误信息")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "本地模型运行任务"
        verbose_name_plural = "本地模型运行任务"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.config_id} {self.action} {self.status}"


class LocalLLMRuntimeState(models.Model):
    """本地模型运行状态（持久化）。"""

    STATUS_INACTIVE = "inactive"
    STATUS_ACTIVATING = "activating"
    STATUS_ACTIVE = "active"
    STATUS_DEACTIVATING = "deactivating"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_INACTIVE, "未激活"),
        (STATUS_ACTIVATING, "激活中"),
        (STATUS_ACTIVE, "已激活"),
        (STATUS_DEACTIVATING, "取消激活中"),
        (STATUS_FAILED, "失败"),
    ]

    config = models.OneToOneField(
        LocalLLMConfig,
        on_delete=models.CASCADE,
        related_name="runtime_state",
        verbose_name="本地模型配置",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_INACTIVE,
        verbose_name="模型状态",
    )
    current_action = models.CharField(max_length=20, blank=True, verbose_name="当前动作")
    is_busy = models.BooleanField(default=False, verbose_name="是否忙碌")
    last_message = models.TextField(blank=True, verbose_name="最近状态说明")
    last_error = models.TextField(blank=True, verbose_name="最近错误")
    last_task = models.ForeignKey(
        LocalLLMRuntimeTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="state_refs",
        verbose_name="最近任务",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "本地模型运行状态"
        verbose_name_plural = "本地模型运行状态"

    def __str__(self):
        return f"{self.config_id} {self.status}"


class Project(models.Model):
    """项目管理模型"""
    name = models.CharField(max_length=100, verbose_name="项目名称")
    path = models.CharField(max_length=500, verbose_name="项目路径", help_text="项目根目录路径，需求文档将保存到该目录下的 doc/01-or 文件夹")
    description = models.TextField(blank=True, verbose_name="项目描述")
    is_default = models.BooleanField(default=False, verbose_name="是否默认项目")
    llm_model = models.ForeignKey(
        LLMModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="默认大模型",
        help_text="项目默认使用的大语言模型，不设置则使用系统默认模型"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")


    class Meta:
        ordering = ["-is_default", "-updated_at"]
        verbose_name = "项目"
        verbose_name_plural = "项目"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        # 确保路径是绝对路径
        if self.path:
            self.path = os.path.abspath(self.path)
        # 如果设置为默认项目，取消其他项目的默认状态
        if self.is_default:
            Project.objects.filter(created_by=self.created_by, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    @property
    def or_path(self):
        """获取原始需求文档路径 (项目路径/doc/01-or)"""
        return os.path.join(self.path, 'doc', '01-or')

    def ensure_or_path_exists(self):
        """确保原始需求文档目录存在"""
        or_path = self.or_path
        if not os.path.exists(or_path):
            os.makedirs(or_path, exist_ok=True)
        return or_path

    def initialize_project_structure(self):
        """初始化项目目录结构，复制关键目录和 AGENTS.md"""
        import shutil

        # 确保项目根目录存在
        if not os.path.exists(self.path):
            os.makedirs(self.path, exist_ok=True)

        # 创建 doc 目录
        doc_path = os.path.join(self.path, 'doc')
        if not os.path.exists(doc_path):
            os.makedirs(doc_path, exist_ok=True)

        # 创建 tools 目录
        tools_path = os.path.join(self.path, 'tools')
        if not os.path.exists(tools_path):
            os.makedirs(tools_path, exist_ok=True)

        # 创建 data/roles 目录（角色约束目录已下沉到 data）
        data_path = os.path.join(self.path, 'data')
        roles_path = os.path.join(data_path, 'roles')
        os.makedirs(roles_path, exist_ok=True)

        # 从 core 项目同步 data/roles 目录内容
        core_roles_dir = os.path.join(self.get_core_project_path(), 'data', 'roles')
        if os.path.isdir(core_roles_dir):
            for entry in os.listdir(core_roles_dir):
                src = os.path.join(core_roles_dir, entry)
                dst = os.path.join(roles_path, entry)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                elif not os.path.exists(dst):
                    shutil.copy2(src, dst)

        # 复制 AGENTS.md 从 core 项目
        core_agents_path = os.path.join(self.get_core_project_path(), 'AGENTS.md')
        new_agents_path = os.path.join(self.path, 'AGENTS.md')
        if os.path.exists(core_agents_path) and not os.path.exists(new_agents_path):
            shutil.copy2(core_agents_path, new_agents_path)

        # 确保需求文档目录存在
        self.ensure_or_path_exists()

        return {
            'doc_path': doc_path,
            'tools_path': tools_path,
            'data_path': data_path,
            'roles_path': roles_path,
            'agents_path': new_agents_path,
        }

    @classmethod
    def get_core_project_path(cls):
        """获取 core 项目的路径"""
        return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

    @classmethod
    def get_projects_base_path(cls):
        """获取项目基础路径（core 的父目录）"""
        return os.path.dirname(cls.get_core_project_path())

    @classmethod
    def get_default_project(cls, user):
        """获取用户的默认项目，如果没有则创建core项目"""
        project = cls.objects.filter(created_by=user, is_default=True).first()
        if not project:
            # 创建默认的core项目，路径指向 core 目录（项目根目录）
            core_project_path = cls.get_core_project_path()
            project, _ = cls.objects.get_or_create(
                created_by=user,
                is_default=True,
                defaults={
                    'name': 'core',
                    'path': core_project_path,
                    'description': '默认项目'
                }
            )
            # 确保需求文档目录存在
            project.ensure_or_path_exists()
        return project


def _normalize_companion_modules_text(raw_text: str) -> str:
    values = []
    for raw in str(raw_text or "").split(","):
        token = str(raw).strip().lower()
        if not token:
            continue
        if token in values:
            continue
        values.append(token)
    return ",".join(values)


def _normalize_companion_paths_text(raw_text: str) -> str:
    values = []
    for raw in str(raw_text or "").split(","):
        token = str(raw).strip().lower()
        if not token:
            continue
        if token in values:
            continue
        values.append(token)
    return ",".join(values)


def _safe_companion_path_fragment(raw_value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(raw_value or "").strip()).strip("-").lower()
    return normalized[:80]


def _build_companion_knowledge_relpath(companion_name: str) -> str:
    fragment = _safe_companion_path_fragment(companion_name) or "companion"
    return f"data/companions/{fragment}/knowledge"


class CompanionProfile(models.Model):
    """伙伴配置（伙伴不等同于智能体目录，而是可配置角色主体）。"""

    LLM_ROUTING_MANUAL = "manual"
    LLM_ROUTING_AUTO = "auto"
    LLM_ROUTING_CHOICES = [
        (LLM_ROUTING_MANUAL, "手动模式"),
        (LLM_ROUTING_AUTO, "自动模式"),
    ]

    LLM_SOURCE_API = "api"
    LLM_SOURCE_LOCAL = "local"
    LLM_SOURCE_CHOICES = [
        (LLM_SOURCE_API, "大模型 API"),
        (LLM_SOURCE_LOCAL, "本地模型"),
    ]

    name = models.CharField(max_length=80, verbose_name="伙伴标识")
    display_name = models.CharField(max_length=120, blank=True, verbose_name="展示名称")
    role_title = models.CharField(max_length=120, blank=True, verbose_name="角色名称")
    persona = models.TextField(blank=True, verbose_name="角色描述")
    tone = models.CharField(max_length=120, blank=True, verbose_name="回复语气")
    memory_notes = models.TextField(blank=True, verbose_name="记忆摘要")
    llm_routing_mode = models.CharField(
        max_length=20,
        choices=LLM_ROUTING_CHOICES,
        default=LLM_ROUTING_MANUAL,
        verbose_name="模型路由模式",
    )
    llm_source_type = models.CharField(
        max_length=20,
        choices=LLM_SOURCE_CHOICES,
        default=LLM_SOURCE_API,
        verbose_name="模型来源",
    )
    llm_api_config = models.ForeignKey(
        LLMApiConfig,
        on_delete=models.SET_NULL,
        related_name="companion_profiles",
        null=True,
        blank=True,
        verbose_name="API 模型配置",
    )
    local_llm_config = models.ForeignKey(
        LocalLLMConfig,
        on_delete=models.SET_NULL,
        related_name="companion_profiles",
        null=True,
        blank=True,
        verbose_name="本地模型配置",
    )
    default_model_name = models.CharField(max_length=120, blank=True, verbose_name="默认使用模型")
    backup_model_tokens = models.JSONField(default=list, blank=True, verbose_name="备用模型列表")
    allowed_agent_modules_text = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="可调用智能体模块",
        help_text="逗号分隔，如 mindforge,helm",
    )
    allowed_control_modules_text = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="可调用工具组件模块",
        help_text="逗号分隔，如 observe,handle",
    )
    allowed_toolsets_text = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="可调用工具集",
        help_text="逗号分隔，如 component_call_tool,knowledge_curation_tool",
    )
    allowed_control_components_text = models.TextField(
        blank=True,
        verbose_name="可调用组件",
        help_text="逗号分隔 component_key，如 handle.file_reader_component",
    )
    allowed_control_functions_text = models.TextField(
        blank=True,
        verbose_name="可调用组件 API",
        help_text="逗号分隔函数路径，如 component.observe.understand_current_screen",
    )
    knowledge_path = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="知识库路径",
        help_text="相对项目根目录，如 data/companions/er-gou/knowledge",
    )
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="companions",
        verbose_name="所属项目",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="companions",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "伙伴配置"
        verbose_name_plural = "伙伴配置"
        ordering = ["-updated_at", "name"]
        constraints = [
            models.UniqueConstraint(fields=["created_by", "project", "name"], name="uniq_user_project_companion"),
        ]

    def __str__(self) -> str:
        return self.display_name or self.name

    def save(self, *args, **kwargs):
        self.name = str(self.name or "").strip()
        self.display_name = str(self.display_name or "").strip()
        self.llm_routing_mode = str(self.llm_routing_mode or self.LLM_ROUTING_MANUAL).strip() or self.LLM_ROUTING_MANUAL
        self.default_model_name = str(self.default_model_name or "").strip()
        if not isinstance(self.backup_model_tokens, list):
            self.backup_model_tokens = []
        normalized_backup = []
        for item in self.backup_model_tokens:
            token = str(item or "").strip()
            if not token or token in normalized_backup:
                continue
            normalized_backup.append(token)
        self.backup_model_tokens = normalized_backup
        self.allowed_agent_modules_text = _normalize_companion_modules_text(self.allowed_agent_modules_text)
        self.allowed_control_modules_text = _normalize_companion_modules_text(self.allowed_control_modules_text)
        self.allowed_toolsets_text = _normalize_companion_modules_text(self.allowed_toolsets_text)
        self.allowed_control_components_text = _normalize_companion_paths_text(self.allowed_control_components_text)
        self.allowed_control_functions_text = _normalize_companion_paths_text(self.allowed_control_functions_text)
        self.llm_source_type = str(self.llm_source_type or self.LLM_SOURCE_API).strip() or self.LLM_SOURCE_API
        if self.llm_routing_mode == self.LLM_ROUTING_AUTO:
            self.llm_api_config = None
            self.local_llm_config = None
            self.default_model_name = ""
            self.backup_model_tokens = []
        self.knowledge_path = _build_companion_knowledge_relpath(self.name)
        self.knowledge_path = str(self.knowledge_path or "").strip().replace("\\", "/").lstrip("/")
        super().save(*args, **kwargs)
        self._ensure_knowledge_dir_exists()

    def _ensure_knowledge_dir_exists(self):
        if not self.project_id:
            return
        project_root_text = str(getattr(self.project, "path", "") or "").strip()
        if not project_root_text:
            return
        project_root = Path(project_root_text)
        target_dir = (project_root / self.knowledge_path).resolve()
        project_root_real = project_root.resolve()
        if target_dir != project_root_real and not str(target_dir).startswith(f"{project_root_real}{os.sep}"):
            return
        target_dir.mkdir(parents=True, exist_ok=True)

    def clean(self):
        super().clean()
        routing_mode = str(self.llm_routing_mode or "").strip() or self.LLM_ROUTING_MANUAL
        if routing_mode not in {self.LLM_ROUTING_MANUAL, self.LLM_ROUTING_AUTO}:
            raise ValidationError({"llm_routing_mode": "模型路由模式不合法。"})

        if routing_mode == self.LLM_ROUTING_AUTO:
            self.llm_api_config = None
            self.local_llm_config = None
            self.default_model_name = ""
            self.backup_model_tokens = []
            return

        source = str(self.llm_source_type or "").strip()
        if source not in {self.LLM_SOURCE_API, self.LLM_SOURCE_LOCAL}:
            raise ValidationError({"llm_source_type": "模型来源不合法。"})

        if source == self.LLM_SOURCE_API:
            if not self.llm_api_config_id:
                raise ValidationError({"llm_api_config": "请选择 API 模型配置。"})
            self.local_llm_config = None
        elif source == self.LLM_SOURCE_LOCAL:
            if not self.local_llm_config_id:
                raise ValidationError({"local_llm_config": "请选择本地模型配置。"})
            self.llm_api_config = None

        if not isinstance(self.backup_model_tokens, list):
            raise ValidationError({"backup_model_tokens": "备用模型列表格式不合法。"})
        dedup_tokens = []
        for raw in self.backup_model_tokens:
            token = str(raw or "").strip()
            if not token or token in dedup_tokens:
                continue
            dedup_tokens.append(token)
        self.backup_model_tokens = dedup_tokens
        if str(self.default_model_name or "").strip():
            config_id = self.llm_api_config_id if source == self.LLM_SOURCE_API else self.local_llm_config_id
            default_token = f"{source}|{config_id}|{str(self.default_model_name or '').strip()}"
            if default_token in self.backup_model_tokens:
                raise ValidationError({"backup_model_tokens": "备用模型不能与默认模型重复。"})

    def get_allowed_agent_modules(self):
        return [item for item in self.allowed_agent_modules_text.split(",") if item]

    def get_allowed_control_modules(self):
        return [item for item in self.allowed_control_modules_text.split(",") if item]

    def get_allowed_toolsets(self):
        return [item for item in self.allowed_toolsets_text.split(",") if item]

    def get_allowed_control_components(self):
        return [item for item in self.allowed_control_components_text.split(",") if item]

    def get_allowed_control_functions(self):
        return [item for item in self.allowed_control_functions_text.split(",") if item]


class RequirementSession(models.Model):
    # 会话阶段
    PHASE_COLLECTING = "collecting"  # 第一阶段：收集需求
    PHASE_ORGANIZING = "organizing"  # 第二阶段：整理需求
    PHASE_COMPLETED = "completed"    # 已完成
    PHASE_CHOICES = [
        (PHASE_COLLECTING, "需求收集中"),
        (PHASE_ORGANIZING, "需求整理中"),
        (PHASE_COMPLETED, "已完成"),
    ]

    title = models.CharField(max_length=200, verbose_name="标题")
    # 兼容历史结构保留字段，多轮消息内容存储在 RequirementMessage。
    content = models.TextField(verbose_name="原始需求内容")
    phase = models.CharField(
        max_length=20,
        choices=PHASE_CHOICES,
        default=PHASE_COLLECTING,
        verbose_name="会话阶段"
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="sessions",
        verbose_name="所属项目",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="requirement_sessions",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "需求会话"
        verbose_name_plural = "需求会话"

    def __str__(self) -> str:
        return self.title


class RequirementMessage(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [
        (ROLE_USER, "用户"),
        (ROLE_ASSISTANT, "助手"),
    ]

    session = models.ForeignKey(
        RequirementSession,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="所属会话",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name="角色")
    content = models.TextField(verbose_name="消息内容")
    attachment = models.FileField(upload_to="chat_attachments/", blank=True, null=True, verbose_name="上传附件")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        ordering = ["created_at"]
        verbose_name = "需求消息"
        verbose_name_plural = "需求消息"

    def __str__(self) -> str:
        return f"{self.get_role_display()} - {self.session_id}"

    @property
    def attachment_mime_type(self):
        if not self.attachment:
            return ""
        mime_type, _ = mimetypes.guess_type(self.attachment.name)
        return (mime_type or "").lower()

    @property
    def is_audio_attachment(self):
        return self.attachment_mime_type.startswith("audio/")


class ChatReplyTask(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_STOPPED = "stopped"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "等待中"),
        (STATUS_RUNNING, "生成中"),
        (STATUS_COMPLETED, "已完成"),
        (STATUS_STOPPED, "已停止"),
        (STATUS_FAILED, "失败"),
    ]

    session = models.ForeignKey(
        RequirementSession,
        on_delete=models.CASCADE,
        related_name="reply_tasks",
        verbose_name="所属会话",
    )
    user_message = models.ForeignKey(
        RequirementMessage,
        on_delete=models.CASCADE,
        related_name="reply_tasks_as_prompt",
        verbose_name="用户消息",
    )
    assistant_message = models.ForeignKey(
        RequirementMessage,
        on_delete=models.CASCADE,
        related_name="reply_tasks_as_reply",
        verbose_name="助手消息",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_reply_tasks",
        verbose_name="创建人",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="状态",
    )
    stop_requested = models.BooleanField(default=False, verbose_name="是否请求停止")
    error_message = models.TextField(blank=True, verbose_name="错误信息")
    execution_trace = models.JSONField(default=dict, blank=True, verbose_name="执行轨迹")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "聊天回复任务"
        verbose_name_plural = "聊天回复任务"
        ordering = ["-created_at"]

    def __str__(self):
        return f"session={self.session_id}, status={self.status}"


class CommunicationChannelConfig(models.Model):
    """通信渠道配置（用于组件读取敏感参数）。"""

    PROVIDER_DINGTALK = "dingtalk"
    PROVIDER_WECOM = "wecom"
    PROVIDER_FEISHU = "feishu"
    PROVIDER_CHOICES = [
        (PROVIDER_DINGTALK, "钉钉"),
        (PROVIDER_WECOM, "企业微信"),
        (PROVIDER_FEISHU, "飞书"),
    ]

    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, verbose_name="通信平台")
    name = models.CharField(max_length=100, verbose_name="配置名称", help_text="同一通信平台内唯一")
    display_name = models.CharField(max_length=200, blank=True, verbose_name="展示名称")
    is_enabled = models.BooleanField(default=True, verbose_name="是否启用")
    config = models.JSONField(default=dict, blank=True, verbose_name="配置内容")
    description = models.TextField(blank=True, verbose_name="说明")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "通信配置"
        verbose_name_plural = "通信配置"
        ordering = ["provider", "name"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "name"], name="uniq_provider_name"),
        ]

    def __str__(self):
        return f"{self.get_provider_display()} - {self.name}"


class ComponentSystemParamConfig(models.Model):
    """组件系统参数配置（通用，字段由组件 Schema 决定）。"""

    module_name = models.CharField(max_length=100, verbose_name="模块名")
    component_key = models.CharField(max_length=200, verbose_name="组件标识")
    config_name = models.CharField(max_length=100, verbose_name="配置名", help_text="同一组件内唯一，如 test/prod")
    display_name = models.CharField(max_length=200, blank=True, verbose_name="展示名称")
    is_enabled = models.BooleanField(default=True, verbose_name="是否启用")
    params = models.JSONField(default=dict, blank=True, verbose_name="参数值")
    schema_snapshot = models.JSONField(default=dict, blank=True, verbose_name="Schema 快照")
    description = models.TextField(blank=True, verbose_name="说明")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "组件系统参数配置"
        verbose_name_plural = "组件系统参数配置"
        ordering = ["module_name", "component_key", "config_name"]
        constraints = [
            models.UniqueConstraint(fields=["component_key", "config_name"], name="uniq_component_config_name"),
        ]

    def __str__(self):
        return f"{self.component_key} - {self.config_name}"


class ComponentSystemPermissionGrant(models.Model):
    """组件系统权限确认记录（用于页面侧声明与运行前校验）。"""

    module_name = models.CharField(max_length=100, verbose_name="模块名")
    component_key = models.CharField(max_length=200, verbose_name="组件标识")
    permission_key = models.CharField(max_length=200, verbose_name="权限标识")
    permission_name = models.CharField(max_length=200, blank=True, verbose_name="权限名称")
    is_granted = models.BooleanField(default=False, verbose_name="是否已授予")
    grant_note = models.TextField(blank=True, verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "组件系统权限确认"
        verbose_name_plural = "组件系统权限确认"
        ordering = ["module_name", "component_key", "permission_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["component_key", "permission_key"],
                name="uniq_component_permission_key",
            ),
        ]

    def __str__(self):
        return f"{self.component_key} - {self.permission_key}"


class ControlApiTestTask(models.Model):
    """组件 API 测试异步任务。"""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "等待中"),
        (STATUS_RUNNING, "执行中"),
        (STATUS_SUCCESS, "成功"),
        (STATUS_FAILED, "失败"),
    ]

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="control_api_test_tasks",
        verbose_name="创建人",
    )
    module_name = models.CharField(max_length=100, verbose_name="模块名")
    function_path = models.CharField(max_length=500, verbose_name="函数路径")
    component_key = models.CharField(max_length=200, blank=True, verbose_name="组件标识")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="状态",
    )
    call_kwargs_text = models.TextField(blank=True, verbose_name="调用入参（脱敏）")
    call_result_text = models.TextField(blank=True, verbose_name="执行结果（脱敏）")
    error_message = models.TextField(blank=True, verbose_name="错误信息")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "组件 API 测试任务"
        verbose_name_plural = "组件 API 测试任务"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.module_name} | {self.function_path} | {self.status}"
