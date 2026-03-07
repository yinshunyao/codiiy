from django.db import migrations, models
import django.db.models.deletion


def backfill_messages(apps, schema_editor):
    requirement_session = apps.get_model("collector", "RequirementSession")
    requirement_message = apps.get_model("collector", "RequirementMessage")

    for session in requirement_session.objects.all():
        has_messages = requirement_message.objects.filter(session_id=session.id).exists()
        if has_messages:
            continue
        legacy_content = (session.content or "").strip()
        if not legacy_content:
            continue
        requirement_message.objects.create(
            session_id=session.id,
            role="user",
            content=legacy_content,
        )
        requirement_message.objects.create(
            session_id=session.id,
            role="assistant",
            content="收到",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("collector", "0002_create_default_admin"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="requirementsession",
            options={
                "ordering": ["-updated_at"],
                "verbose_name": "需求会话",
                "verbose_name_plural": "需求会话",
            },
        ),
        migrations.CreateModel(
            name="RequirementMessage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[("user", "用户"), ("assistant", "助手")],
                        max_length=20,
                        verbose_name="角色",
                    ),
                ),
                ("content", models.TextField(verbose_name="消息内容")),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="创建时间"),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="collector.requirementsession",
                        verbose_name="所属会话",
                    ),
                ),
            ],
            options={
                "verbose_name": "需求消息",
                "verbose_name_plural": "需求消息",
                "ordering": ["created_at"],
            },
        ),
        migrations.RunPython(backfill_messages, migrations.RunPython.noop),
    ]
