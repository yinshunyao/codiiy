import os
import unittest
from pathlib import Path

from core.reqcollector.path_bootstrap import (
    DEFAULT_PROJECT_ROOT,
    configure_process_project_root,
    extract_project_root_arg,
    resolve_project_root,
)


class PathBootstrapTestCase(unittest.TestCase):
    def test_resolve_project_root_should_use_default_when_empty(self):
        resolved = resolve_project_root("")
        self.assertEqual(resolved, DEFAULT_PROJECT_ROOT.resolve())

    def test_resolve_project_root_should_resolve_relative_against_default(self):
        resolved = resolve_project_root("tmp/demo")
        expected = (DEFAULT_PROJECT_ROOT / "tmp/demo").resolve()
        self.assertEqual(resolved, expected)

    def test_extract_project_root_arg_should_support_equal_style(self):
        argv = ["manage.py", "runserver", "--project-dir=/tmp/demo", "--noreload"]
        normalized, project_dir = extract_project_root_arg(argv)
        self.assertEqual(project_dir, "/tmp/demo")
        self.assertEqual(normalized, ["manage.py", "runserver", "--noreload"])

    def test_extract_project_root_arg_should_support_split_style(self):
        argv = ["manage.py", "runserver", "--project-dir", "tmp/demo", "--noreload"]
        normalized, project_dir = extract_project_root_arg(argv)
        self.assertEqual(project_dir, "tmp/demo")
        self.assertEqual(normalized, ["manage.py", "runserver", "--noreload"])

    def test_configure_process_project_root_should_write_env(self):
        old_env = os.environ.get("CODIIY_PROJECT_ROOT")
        old_cwd = os.getcwd()
        try:
            target = configure_process_project_root("tmp/bootstrap-test")
            self.assertEqual(os.environ.get("CODIIY_PROJECT_ROOT"), str(target))
            self.assertEqual(Path(os.getcwd()).resolve(), target)
        finally:
            os.chdir(old_cwd)
            if old_env is None:
                os.environ.pop("CODIIY_PROJECT_ROOT", None)
            else:
                os.environ["CODIIY_PROJECT_ROOT"] = old_env
