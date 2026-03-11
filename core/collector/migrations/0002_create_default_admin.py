from django.contrib.auth.hashers import make_password
from django.db import migrations


def create_default_admin(apps, schema_editor):
    user_model = apps.get_model("auth", "User")
    if user_model.objects.exists():
        return
    user_model.objects.create(
        username="admin",
        is_superuser=True,
        is_staff=True,
        is_active=True,
        password=make_password("123456"),
    )


def reverse_create_default_admin(apps, schema_editor):
    user_model = apps.get_model("auth", "User")
    user_model.objects.filter(username="admin").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("collector", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_admin, reverse_create_default_admin),
    ]
