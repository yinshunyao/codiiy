from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("collector", "0014_componentsystempermissiongrant"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ControlApiTestTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("module_name", models.CharField(max_length=100, verbose_name="模块名")),
                ("function_path", models.CharField(max_length=500, verbose_name="函数路径")),
                ("component_key", models.CharField(blank=True, max_length=200, verbose_name="组件标识")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "等待中"), ("running", "执行中"), ("success", "成功"), ("failed", "失败")],
                        default="pending",
                        max_length=20,
                        verbose_name="状态",
                    ),
                ),
                ("call_kwargs_text", models.TextField(blank=True, verbose_name="调用入参（脱敏）")),
                ("call_result_text", models.TextField(blank=True, verbose_name="执行结果（脱敏）")),
                ("error_message", models.TextField(blank=True, verbose_name="错误信息")),
                ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="开始时间")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="结束时间")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="control_api_test_tasks",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="创建人",
                    ),
                ),
            ],
            options={
                "verbose_name": "组件 API 测试任务",
                "verbose_name_plural": "组件 API 测试任务",
                "ordering": ["-created_at"],
            },
        ),
    ]
