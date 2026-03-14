from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("collector", "0023_merge_20260314_1756"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatreplytask",
            name="execution_trace",
            field=models.JSONField(blank=True, default=dict, verbose_name="执行轨迹"),
        ),
    ]

