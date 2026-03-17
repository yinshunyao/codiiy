from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("collector", "0015_controlapitesttask"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanionProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, verbose_name="伙伴标识")),
                ("display_name", models.CharField(blank=True, max_length=120, verbose_name="展示名称")),
                ("role_title", models.CharField(blank=True, max_length=120, verbose_name="角色名称")),
                ("persona", models.TextField(blank=True, verbose_name="角色描述")),
                ("tone", models.CharField(blank=True, max_length=120, verbose_name="回复语气")),
                ("memory_notes", models.TextField(blank=True, verbose_name="记忆摘要")),
                (
                    "allowed_agent_modules_text",
                    models.CharField(
                        blank=True,
                        help_text="逗号分隔，如 mindforge,skills",
                        max_length=200,
                        verbose_name="可调用智能体模块",
                    ),
                ),
                (
                    "allowed_control_modules_text",
                    models.CharField(
                        blank=True,
                        help_text="逗号分隔，如 observe,handle",
                        max_length=200,
                        verbose_name="可调用组件模块",
                    ),
                ),
                (
                    "knowledge_path",
                    models.CharField(
                        blank=True,
                        help_text="相对项目根目录，如 data/companions/er-gou/knowledge",
                        max_length=300,
                        verbose_name="知识库路径",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="是否启用")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="companions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="创建人",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="companions",
                        to="collector.project",
                        verbose_name="所属项目",
                    ),
                ),
            ],
            options={
                "verbose_name": "伙伴配置",
                "verbose_name_plural": "伙伴配置",
                "ordering": ["-updated_at", "name"],
            },
        ),
        migrations.AddConstraint(
            model_name="companionprofile",
            constraint=models.UniqueConstraint(fields=("created_by", "project", "name"), name="uniq_user_project_companion"),
        ),
    ]
