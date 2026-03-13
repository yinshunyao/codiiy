import os
import mimetypes
from django.conf import settings
from django.db import models



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
        (ROLE_ASSISTANT, "小柯"),
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
