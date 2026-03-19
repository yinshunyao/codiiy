import os
import sys
import unittest

import django
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))
CORE_ROOT = os.path.join(PROJECT_ROOT, "core")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if CORE_ROOT not in sys.path:
    sys.path.insert(0, CORE_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.reqcollector.settings")
django.setup()

from collector import views
from collector.models import CompanionProfile, Project, RequirementMessage, RequirementSession


class CollectorViewsTokenTraceTestCase(unittest.TestCase):
    def test_realtime_trace_event_should_extract_and_merge_token_usage(self):
        process_trace = views._new_process_trace()
        event_payload = {
            "kind": "llm_call",
            "title": "ReAct step 1 推理调用结束",
            "status": "success",
            "output": {
                "duration_ms": 1200,
                "token_usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 5,
                },
            },
            "error": "",
        }

        views._append_realtime_trace_event_and_merge_token(
            process_trace=process_trace,
            event_payload=event_payload,
        )

        self.assertEqual(len(process_trace.get("events") or []), 1)
        first_event = (process_trace.get("events") or [])[0]
        self.assertEqual(
            first_event.get("token_usage"),
            {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        )
        self.assertEqual(
            process_trace.get("token_usage"),
            {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        )

    def test_realtime_trace_event_should_support_top_level_token_usage(self):
        process_trace = views._new_process_trace()
        first_event = {
            "kind": "llm_call",
            "title": "step 1",
            "status": "success",
            "token_usage": {"prompt_tokens": 2, "completion_tokens": 3},
        }
        second_event = {
            "kind": "llm_call",
            "title": "step 2",
            "status": "success",
            "token_usage": {"prompt_tokens": "4", "completion_tokens": "1", "total_tokens": "5"},
        }

        views._append_realtime_trace_event_and_merge_token(
            process_trace=process_trace,
            event_payload=first_event,
        )
        views._append_realtime_trace_event_and_merge_token(
            process_trace=process_trace,
            event_payload=second_event,
        )

        self.assertEqual(
            process_trace.get("token_usage"),
            {"prompt_tokens": 6, "completion_tokens": 4, "total_tokens": 10},
        )

    def test_build_tool_method_param_fields_should_extract_required_and_types(self):
        def sample_method(
            dir_path: str,
            create_parent_dirs: bool = True,
            retries: int = 1,
            ratio: float = 0.5,
            options: dict = None,
        ):
            return dir_path

        fields = views._build_tool_method_param_fields(sample_method)
        field_map = {item["name"]: item for item in fields}

        self.assertTrue(field_map["dir_path"]["required"])
        self.assertEqual(field_map["create_parent_dirs"]["value_type"], "bool")
        self.assertEqual(field_map["retries"]["value_type"], "int")
        self.assertEqual(field_map["ratio"]["value_type"], "float")
        self.assertEqual(field_map["options"]["value_type"], "json")

    def test_parse_demo_param_value_should_convert_bool_for_tool_test(self):
        field = {
            "name": "create_parent_dirs",
            "required": False,
            "value_type": "bool",
        }
        ok, parsed_value, error = views._parse_demo_param_value(field, "false")
        self.assertTrue(ok)
        self.assertFalse(parsed_value)
        self.assertEqual(error, "")


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ProjectListViewTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="project-list-user",
            password="pass-123456",
        )
        self.client.login(username="project-list-user", password="pass-123456")
        self.default_project = Project.objects.create(
            name="core",
            path=".",
            created_by=self.user,
            is_default=True,
        )
        self.secondary_project = Project.objects.create(
            name="project-b",
            path="tmp/project-b",
            created_by=self.user,
            is_default=False,
        )

    def test_project_list_should_not_render_top_flash_messages(self):
        response = self.client.get(
            reverse("project_set_default", args=[self.secondary_project.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "我的项目")
        self.assertNotContains(
            response,
            f"项目 '{self.secondary_project.name}' 已设为默认项目",
        )


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class CompactListLayoutViewTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="compact-layout-user",
            password="pass-123456",
        )
        self.client.login(username="compact-layout-user", password="pass-123456")
        Project.objects.create(
            name="core",
            path=".",
            created_by=self.user,
            is_default=True,
        )

    def test_toolset_list_should_render_compact_row_layout(self):
        response = self.client.get(reverse("toolset_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "toolset-item-header")
        self.assertContains(response, "toolset-meta-row")
        self.assertContains(response, "toolset-item-actions")
        self.assertContains(response, "测试")

    def test_agent_item_list_should_render_compact_row_layout(self):
        module_name = next(iter(views.ALLOWED_AGENT_MODULES.keys()))
        response = self.client.get(reverse("agent_item_list", args=[module_name]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "agent-meta-row")
        self.assertContains(response, "摘要：")


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class SessionMessageDeleteViewTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="msg-delete-user",
            password="pass-123456",
        )
        self.client.login(username="msg-delete-user", password="pass-123456")
        self.project = Project.objects.create(
            name="core",
            path=".",
            created_by=self.user,
            is_default=True,
        )

    def test_should_delete_single_message_in_main_chat(self):
        session_obj = RequirementSession.objects.create(
            title="主聊天",
            content=views.MAIN_CHAT_SESSION_MARKER,
            created_by=self.user,
            project=self.project,
        )
        msg_keep = RequirementMessage.objects.create(
            session=session_obj,
            role=RequirementMessage.ROLE_USER,
            content="保留消息",
        )
        msg_delete = RequirementMessage.objects.create(
            session=session_obj,
            role=RequirementMessage.ROLE_ASSISTANT,
            content="待删除消息",
        )

        response = self.client.post(
            reverse("session_message_delete", args=[session_obj.id, msg_delete.id]),
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("session_list"))
        self.assertTrue(RequirementMessage.objects.filter(id=msg_keep.id).exists())
        self.assertFalse(RequirementMessage.objects.filter(id=msg_delete.id).exists())

    def test_should_delete_single_message_in_companion_chat(self):
        companion = CompanionProfile.objects.create(
            name="er-gou",
            display_name="二狗",
            created_by=self.user,
            project=self.project,
            llm_source_type=CompanionProfile.LLM_SOURCE_API,
            llm_routing_mode=CompanionProfile.LLM_ROUTING_AUTO,
            is_active=True,
        )
        session_obj = RequirementSession.objects.create(
            title="伙伴会话",
            content=views._build_companion_chat_session_marker(companion.id),
            created_by=self.user,
            project=self.project,
        )
        msg_delete = RequirementMessage.objects.create(
            session=session_obj,
            role=RequirementMessage.ROLE_USER,
            content="伙伴会话消息",
        )

        response = self.client.post(
            reverse("session_message_delete", args=[session_obj.id, msg_delete.id]),
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("companion_chat", args=[companion.id]))
        self.assertFalse(RequirementMessage.objects.filter(id=msg_delete.id).exists())

    def test_should_forbid_cross_user_message_delete(self):
        other_user = get_user_model().objects.create_user(
            username="msg-delete-other",
            password="pass-123456",
        )
        other_project = Project.objects.create(
            name="other-core",
            path=".",
            created_by=other_user,
            is_default=True,
        )
        other_session = RequirementSession.objects.create(
            title="他人会话",
            content=views.MAIN_CHAT_SESSION_MARKER,
            created_by=other_user,
            project=other_project,
        )
        target_message = RequirementMessage.objects.create(
            session=other_session,
            role=RequirementMessage.ROLE_USER,
            content="他人消息",
        )

        response = self.client.post(
            reverse("session_message_delete", args=[other_session.id, target_message.id]),
            follow=False,
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(RequirementMessage.objects.filter(id=target_message.id).exists())

    def test_session_list_should_render_rollback_and_delete_actions_in_one_row(self):
        session_obj = RequirementSession.objects.create(
            title="操作按钮布局",
            content=views.MAIN_CHAT_SESSION_MARKER,
            created_by=self.user,
            project=self.project,
        )
        target_message = RequirementMessage.objects.create(
            session=session_obj,
            role=RequirementMessage.ROLE_USER,
            content="测试按钮布局",
        )

        response = self.client.get(reverse("session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="message-action-row"')
        self.assertContains(
            response,
            reverse("session_rollback", args=[session_obj.id, target_message.id]),
        )
        self.assertContains(
            response,
            reverse("session_message_delete", args=[session_obj.id, target_message.id]),
        )


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class MenuNamingSchemeViewTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="menu-naming-user",
            password="pass-123456",
        )
        self.client.login(username="menu-naming-user", password="pass-123456")
        Project.objects.create(
            name="core",
            path=".",
            created_by=self.user,
            is_default=True,
        )

    def test_profile_settings_should_render_menu_naming_selector(self):
        response = self.client.get(reverse("profile_settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "菜单命名方案")
        self.assertContains(response, 'name="menu_naming_scheme"')
        self.assertContains(response, "武侠风")

    def test_session_list_should_render_wuxia_brand_and_companion_under_agent_group(self):
        response = self.client.get(reverse("session_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "开智枢")
        self.assertContains(response, "侠谱")
        self.assertContains(response, "兵刃")
        content_text = response.content.decode("utf-8")
        self.assertGreater(content_text.find("侠谱</a>"), -1)
        self.assertGreater(content_text.find("兵刃</a>"), -1)
        self.assertLess(content_text.find("侠谱</a>"), content_text.find("兵刃</a>"))

    def test_system_settings_should_switch_menu_naming_scheme(self):
        response = self.client.post(
            reverse("system_settings"),
            data={
                "next": reverse("profile_settings"),
                "menu_naming_scheme": "standard",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'title="聊天">聊天')
        self.assertContains(response, "codiiy平台")
        self.assertContains(response, "伙伴管理")
        self.assertContains(response, "工具集")
        content_text = response.content.decode("utf-8")
        self.assertLess(content_text.find("伙伴管理</a>"), content_text.find("工具集</a>"))

        session = self.client.session
        self.assertEqual(session.get("menu_naming_scheme"), "standard")


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class ToolFunctionTestViewTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tool-test-user",
            password="pass-123456",
        )
        self.client.login(username="tool-test-user", password="pass-123456")
        Project.objects.create(
            name="core",
            path=".",
            created_by=self.user,
            is_default=True,
        )

    def test_tool_function_test_page_should_render(self):
        response = self.client.get(reverse("tool_function_test", args=["file_path_tool"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "工具 API 测试")
        self.assertContains(response, "file_path_tool")


if __name__ == "__main__":
    unittest.main()
