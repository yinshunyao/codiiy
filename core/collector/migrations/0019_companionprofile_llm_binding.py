from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("collector", "0018_llmapiconfig_localllmconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="companionprofile",
            name="default_model_name",
            field=models.CharField(blank=True, max_length=120, verbose_name="默认使用模型"),
        ),
        migrations.AddField(
            model_name="companionprofile",
            name="llm_api_config",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="companion_profiles",
                to="collector.llmapiconfig",
                verbose_name="API 模型配置",
            ),
        ),
        migrations.AddField(
            model_name="companionprofile",
            name="llm_source_type",
            field=models.CharField(
                choices=[("api", "大模型 API"), ("local", "本地模型")],
                default="api",
                max_length=20,
                verbose_name="模型来源",
            ),
        ),
        migrations.AddField(
            model_name="companionprofile",
            name="local_llm_config",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="companion_profiles",
                to="collector.localllmconfig",
                verbose_name="本地模型配置",
            ),
        ),
    ]
