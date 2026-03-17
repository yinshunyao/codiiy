import os

from django.core.wsgi import get_wsgi_application

from .path_bootstrap import configure_process_project_root

# 启动前支持通过环境变量覆盖项目目录；缺省时回退到 core 的上一级目录。
configure_process_project_root()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reqcollector.settings")

application = get_wsgi_application()
