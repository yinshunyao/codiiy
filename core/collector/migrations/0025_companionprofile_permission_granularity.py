from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("collector", "0024_chatreplytask_execution_trace"),
    ]

    operations = [
        migrations.AddField(
            model_name="companionprofile",
            name="allowed_control_components_text",
            field=models.TextField(
                blank=True,
                help_text="逗号分隔 component_key，如 handle.file_reader_component",
                verbose_name="可调用组件",
            ),
        ),
        migrations.AddField(
            model_name="companionprofile",
            name="allowed_control_functions_text",
            field=models.TextField(
                blank=True,
                help_text="逗号分隔函数路径，如 component.observe.understand_current_screen",
                verbose_name="可调用组件 API",
            ),
        ),
        migrations.AddField(
            model_name="companionprofile",
            name="allowed_toolsets_text",
            field=models.CharField(
                blank=True,
                help_text="逗号分隔，如 component_call_tool,knowledge_curation_tool",
                max_length=300,
                verbose_name="可调用工具集",
            ),
        ),
    ]

