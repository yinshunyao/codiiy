import os
import sys
from pathlib import Path

from django.core.wsgi import get_wsgi_application

# 兼容 WSGI 场景导入仓库级包（tools/component）。
repo_root = Path(__file__).resolve().parent.parent.parent
repo_root_text = str(repo_root)
if repo_root_text not in sys.path:
    sys.path.insert(0, repo_root_text)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reqcollector.settings")

application = get_wsgi_application()
