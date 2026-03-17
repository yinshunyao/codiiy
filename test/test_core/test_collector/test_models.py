import os
import sys
from pathlib import Path

import django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))
CORE_ROOT = os.path.join(PROJECT_ROOT, "core")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if CORE_ROOT not in sys.path:
    sys.path.insert(0, CORE_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.reqcollector.settings")
django.setup()

from collector.models import Project


class ProjectPathResolutionTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="path-user", password="pass-123456")

    def test_save_should_resolve_relative_path_from_project_root(self):
        project = Project(
            name="rel-path-project",
            path="tmp/project-a",
            created_by=self.user,
        )
        project.save()

        expected = str((Path(settings.PROJECT_ROOT) / "tmp/project-a").resolve())
        self.assertEqual(project.path, expected)

    def test_core_and_projects_base_path_should_use_project_root(self):
        expected_root = str(Path(settings.PROJECT_ROOT).resolve())
        self.assertEqual(Project.get_core_project_path(), expected_root)
        self.assertEqual(Project.get_projects_base_path(), expected_root)
