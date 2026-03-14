from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("collector", "0019_companionprofile_llm_binding"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LocalLLMRuntimeTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("activate", "激活模型"), ("deactivate", "取消激活")], max_length=20, verbose_name="任务动作")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "等待中"),
                            ("running", "执行中"),
                            ("success", "成功"),
                            ("failed", "失败"),
                            ("interrupted", "中断"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="任务状态",
                    ),
                ),
                (
                    "stage",
                    models.CharField(
                        choices=[
                            ("queued", "排队中"),
                            ("pulling", "拉取模型"),
                            ("warming", "加载模型"),
                            ("unloading", "卸载模型"),
                            ("completed", "完成"),
                        ],
                        default="queued",
                        max_length=20,
                        verbose_name="任务阶段",
                    ),
                ),
                ("detail_message", models.TextField(blank=True, verbose_name="状态说明")),
                ("error_message", models.TextField(blank=True, verbose_name="错误信息")),
                ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="开始时间")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="结束时间")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                (
                    "config",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="runtime_tasks",
                        to="collector.localllmconfig",
                        verbose_name="本地模型配置",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="local_llm_runtime_tasks",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="创建人",
                    ),
                ),
            ],
            options={
                "verbose_name": "本地模型运行任务",
                "verbose_name_plural": "本地模型运行任务",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="LocalLLMRuntimeState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("inactive", "未激活"),
                            ("activating", "激活中"),
                            ("active", "已激活"),
                            ("deactivating", "取消激活中"),
                            ("failed", "失败"),
                        ],
                        default="inactive",
                        max_length=20,
                        verbose_name="模型状态",
                    ),
                ),
                ("current_action", models.CharField(blank=True, max_length=20, verbose_name="当前动作")),
                ("is_busy", models.BooleanField(default=False, verbose_name="是否忙碌")),
                ("last_message", models.TextField(blank=True, verbose_name="最近状态说明")),
                ("last_error", models.TextField(blank=True, verbose_name="最近错误")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                (
                    "config",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="runtime_state",
                        to="collector.localllmconfig",
                        verbose_name="本地模型配置",
                    ),
                ),
                (
                    "last_task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="state_refs",
                        to="collector.localllmruntimetask",
                        verbose_name="最近任务",
                    ),
                ),
            ],
            options={
                "verbose_name": "本地模型运行状态",
                "verbose_name_plural": "本地模型运行状态",
            },
        ),
    ]
