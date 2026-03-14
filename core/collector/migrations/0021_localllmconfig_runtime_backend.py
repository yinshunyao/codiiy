from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("collector", "0020_localllmruntimestate_localllmruntimetask"),
    ]

    operations = [
        migrations.AddField(
            model_name="localllmconfig",
            name="llama_cpp_n_ctx",
            field=models.PositiveIntegerField(default=4096, verbose_name="llama-cpp 上下文窗口"),
        ),
        migrations.AddField(
            model_name="localllmconfig",
            name="model_file_path",
            field=models.CharField(
                blank=True,
                help_text="仅 Python 组件模式使用，如 /data/models/qwen2.5-7b-instruct.gguf",
                max_length=500,
                verbose_name="llama-cpp 模型文件路径",
            ),
        ),
        migrations.AddField(
            model_name="localllmconfig",
            name="runtime_backend",
            field=models.CharField(
                choices=[
                    ("ollama", "Ollama 服务"),
                    ("llama_cpp", "Python 组件（llama-cpp-python）"),
                ],
                default="ollama",
                max_length=32,
                verbose_name="本地模型实现模式",
            ),
        ),
        migrations.AlterField(
            model_name="localllmconfig",
            name="endpoint",
            field=models.CharField(blank=True, default="http://127.0.0.1:11434", max_length=300, verbose_name="Ollama 地址"),
        ),
    ]
