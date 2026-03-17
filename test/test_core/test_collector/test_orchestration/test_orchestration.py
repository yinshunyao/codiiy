import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import django

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", "..", ".."))
CORE_ROOT = os.path.join(PROJECT_ROOT, "core")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if CORE_ROOT not in sys.path:
    sys.path.insert(0, CORE_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.reqcollector.settings")
django.setup()

from collector.orchestration.planner import CustomPlanner
from collector.orchestration.coordinator import Coordinator
from collector.orchestration.protocol import ExecutionPlan, PlanStep
from collector.orchestration.service import run_companion_orchestration
from collector.orchestration.mindforge_runner import MindforgeRunner
from collector.orchestration.tool_runner import ToolRunner
from collector.orchestration import capability_search
from agents.mindforge.react_strategy import ReActTool


class OrchestrationTestCase(unittest.TestCase):
    def test_coordinator_should_attach_mindforge_strategy_meta_for_auto_sub_strategies(self):
        payload = {
            "success": True,
            "final_answer": "done",
            "steps": [
                {"thought": "[auto stage plan_execute] execute"},
                {"thought": "[auto stage reflexion] reflect"},
                {"thought": "[auto stage react] fallback"},
            ],
            "error": "",
        }
        enriched = Coordinator._attach_mindforge_strategy_meta(
            output=payload,
            requested_strategy="auto",
        )
        self.assertEqual(enriched.get("mindforge_strategy"), "auto")
        self.assertEqual(
            enriched.get("mindforge_sub_strategies"),
            ["plan_execute", "reflexion", "react"],
        )

    @patch("collector.orchestration.planner.analyzer.chat")
    def test_planner_should_use_llm_dynamic_plan(self, mock_chat):
        mock_chat.return_value = {
            "success": True,
            "response": """{
  "goal": "帮我分析屏幕并给建议",
  "final_strategy": "synthesize_step_outputs",
  "steps": [
    {"step_id": "s1", "step_type": "agent", "target": "mindforge", "input": {"query": "分析屏幕"}, "depends_on": []},
    {"step_id": "s2", "step_type": "tool", "target": "component.observe.understand_current_screen", "input": {"query": "理解当前画面"}, "depends_on": ["s1"]},
    {"step_id": "s3", "step_type": "summarize", "target": "answer_synthesizer", "input": {"query": "总结"}, "depends_on": ["s1", "s2"]}
  ]
}""",
            "error": None,
        }
        planner = CustomPlanner()
        plan = planner.build_plan(
            user_query="帮我分析屏幕并给建议",
            allowed_agent_modules=["mindforge"],
            allowed_control_modules=["observe"],
            allowed_control_components=[],
            allowed_control_functions=[],
            capability_search_mode="hybrid",
            model_id="qwen-plus",
            max_plan_steps=8,
        )
        self.assertGreaterEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].step_type, "agent")
        self.assertEqual(plan.steps[0].target, "mindforge")
        self.assertEqual(plan.steps[1].step_type, "tool")
        self.assertEqual(plan.steps[1].target, "component.observe.understand_current_screen")
        self.assertEqual(plan.steps[-1].step_type, "summarize")

    @patch("collector.orchestration.planner.analyzer.chat")
    def test_planner_should_filter_unrelated_fallback_targets(self, mock_chat):
        mock_chat.return_value = {
            "success": True,
            "response": """{
  "goal": "测试 fallback 过滤",
  "steps": [
    {
      "step_id": "s1",
      "step_type": "tool",
      "target": "component.decide.text_generation",
      "input": {
        "query": "请分析问题",
        "fallback_targets": [
          "component.handle.get_system_info",
          "component.decide.create_qwen_client"
        ]
      },
      "depends_on": []
    }
  ]
}""",
            "error": None,
        }
        planner = CustomPlanner()
        plan = planner.build_plan(
            user_query="请分析问题",
            allowed_agent_modules=[],
            allowed_control_modules=["decide", "handle"],
            allowed_control_components=[],
            allowed_control_functions=[],
            capability_search_mode="hybrid",
            model_id="qwen-plus",
            max_plan_steps=8,
        )
        tool_step = [item for item in plan.steps if item.step_type == "tool"][0]
        fallback_targets = tool_step.input.get("fallback_targets") or []
        self.assertIn("component.decide.create_qwen_client", fallback_targets)
        self.assertNotIn("component.handle.get_system_info", fallback_targets)

    @patch("collector.orchestration.planner.analyzer.chat")
    def test_planner_should_fallback_when_llm_plan_invalid(self, mock_chat):
        mock_chat.return_value = {
            "success": True,
            "response": """{
  "goal": "test",
  "steps": [
    {"step_type": "tool", "target": "component.unknown.bad_tool", "input": {}, "depends_on": []}
  ]
}""",
            "error": None,
        }
        planner = CustomPlanner()
        plan = planner.build_plan(
            user_query="帮我分析",
            allowed_agent_modules=["mindforge", "helm"],
            allowed_control_modules=["observe"],
            allowed_control_components=[],
            allowed_control_functions=[],
            capability_search_mode="hybrid",
            model_id="qwen-plus",
            max_plan_steps=8,
        )
        targets = [item.target for item in plan.steps]
        self.assertIn("mindforge", targets)
        self.assertIn("helm", targets)
        self.assertEqual(plan.steps[-1].step_type, "summarize")

    @patch("collector.orchestration.planner.analyzer.chat")
    def test_planner_should_apply_max_plan_steps_limit(self, mock_chat):
        mock_chat.return_value = {
            "success": True,
            "response": """{
  "goal": "test",
  "steps": [
    {"step_id":"a1","step_type":"agent","target":"mindforge","input":{"query":"1"},"depends_on":[]},
    {"step_id":"a2","step_type":"command","target":"helm","input":{"query":"2"},"depends_on":[]},
    {"step_id":"a3","step_type":"tool","target":"component.observe.understand_current_screen","input":{"query":"3"},"depends_on":["a1"]},
    {"step_id":"a4","step_type":"tool","target":"component.observe.understand_current_screen","input":{"query":"4"},"depends_on":["a3"]},
    {"step_id":"a5","step_type":"summarize","target":"answer_synthesizer","input":{"query":"5"},"depends_on":["a1","a2","a3","a4"]}
  ]
}""",
            "error": None,
        }
        planner = CustomPlanner()
        plan = planner.build_plan(
            user_query="帮我分析",
            allowed_agent_modules=["mindforge", "helm"],
            allowed_control_modules=["observe"],
            allowed_control_components=[],
            allowed_control_functions=[],
            capability_search_mode="hybrid",
            model_id="qwen-plus",
            max_plan_steps=3,
        )
        self.assertEqual(len(plan.steps), 3)
        self.assertEqual(plan.steps[-1].step_type, "summarize")

    @patch("collector.orchestration.planner.analyzer.chat")
    def test_planner_should_build_multi_steps_for_authorized_modules(self, mock_chat):
        mock_chat.return_value = {"success": False, "response": "", "error": "planner llm unavailable"}
        planner = CustomPlanner()
        plan = planner.build_plan(
            user_query="请帮我分析并截图当前界面",
            allowed_agent_modules=["mindforge", "helm"],
            allowed_control_modules=["observe", "decide"],
            allowed_control_components=[],
            allowed_control_functions=[],
        )
        step_types = [item.step_type for item in plan.steps]
        targets = [item.target for item in plan.steps]
        self.assertIn("agent", step_types)
        self.assertIn("command", step_types)
        self.assertIn("summarize", step_types)
        self.assertIn("mindforge", targets)
        self.assertIn("helm", targets)

    @patch("collector.orchestration.planner.search_tool_functions")
    @patch("collector.orchestration.planner.analyzer.chat")
    def test_planner_should_use_lightweight_fast_path_for_disk_query(self, mock_chat, mock_search_tool_functions):
        mock_chat.return_value = {"success": False, "response": "", "error": "planner llm unavailable"}
        mock_search_tool_functions.return_value = (
            [{"path": "tools.file_operator_tool.read_file", "score": 0.91}],
            {"engine_used": "native"},
        )
        planner = CustomPlanner()
        plan = planner.build_plan(
            user_query="帮我查询一下磁盘剩余空间",
            allowed_agent_modules=["mindforge", "helm"],
            allowed_toolsets=["file_operator_tool"],
            allowed_control_modules=[],
            allowed_control_components=[],
            allowed_control_functions=[],
            capability_search_mode="hybrid",
            model_id="qwen-plus",
            max_plan_steps=8,
        )
        step_types = [item.step_type for item in plan.steps]
        targets = [item.target for item in plan.steps]
        self.assertEqual(step_types, ["tool", "summarize"])
        self.assertEqual(targets[0], "tools.file_operator_tool.read_file")
        self.assertNotIn("mindforge", targets)
        self.assertNotIn("helm", targets)
        summarize_input = plan.steps[-1].input or {}
        self.assertFalse(bool(summarize_input.get("enable_completion_signal", True)))

    @patch("collector.orchestration.planner.analyzer.chat")
    def test_planner_should_skip_helm_when_query_not_about_requirement_phase(self, mock_chat):
        mock_chat.return_value = {"success": False, "response": "", "error": "planner llm unavailable"}
        planner = CustomPlanner()
        plan = planner.build_plan(
            user_query="请解释一下这个错误提示",
            allowed_agent_modules=["mindforge", "helm"],
            allowed_toolsets=[],
            allowed_control_modules=[],
            allowed_control_components=[],
            allowed_control_functions=[],
            capability_search_mode="hybrid",
            model_id="qwen-plus",
            max_plan_steps=8,
        )
        targets = [item.target for item in plan.steps]
        self.assertIn("mindforge", targets)
        self.assertNotIn("helm", targets)

    @patch("collector.orchestration.planner.search_tool_functions")
    @patch("collector.orchestration.planner.analyzer.chat")
    def test_planner_should_route_disk_query_to_macos_terminal_run_command(self, mock_chat, mock_search_tool_functions):
        mock_chat.return_value = {"success": False, "response": "", "error": "planner llm unavailable"}
        mock_search_tool_functions.return_value = ([], {"engine_used": "native"})
        planner = CustomPlanner()
        plan = planner.build_plan(
            user_query="请查询当前磁盘剩余空间",
            allowed_agent_modules=["mindforge", "helm"],
            allowed_toolsets=["macos_terminal_tool"],
            allowed_control_modules=[],
            allowed_control_components=[],
            allowed_control_functions=[],
            capability_search_mode="hybrid",
            model_id="qwen-plus",
            max_plan_steps=8,
        )
        self.assertGreaterEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].step_type, "tool")
        self.assertEqual(plan.steps[0].target, "tools.macos_terminal_tool.run_command")
        self.assertEqual(plan.steps[-1].step_type, "summarize")

    @patch("collector.orchestration.planner.search_component_functions")
    @patch("collector.orchestration.planner.analyzer.chat")
    def test_planner_should_skip_disabled_component_function(self, mock_chat, mock_search_component_functions):
        mock_chat.return_value = {"success": False, "response": "", "error": "planner llm unavailable"}
        mock_search_component_functions.return_value = (
            [{"path": "component.observe.understand_current_screen", "score": 0.92}],
            {"engine_used": "native"},
        )
        planner = CustomPlanner()
        with patch.object(
            planner.component_tool,
            "control_call",
            return_value={
                "success": True,
                "data": {
                    "result": [
                        {
                            "module": "observe",
                            "enabled": False,
                            "functions": ["component.observe.understand_current_screen"],
                        }
                    ]
                },
            },
        ):
            plan = planner.build_plan(
                user_query="请分析当前屏幕",
                allowed_agent_modules=[],
                allowed_control_modules=["observe"],
                allowed_control_components=[],
                allowed_control_functions=[],
                capability_search_mode="hybrid",
            )
        tool_steps = [item for item in plan.steps if item.step_type == "tool"]
        self.assertEqual(len(tool_steps), 0)

    def test_tool_runner_should_block_unwhitelisted_module(self):
        runner = ToolRunner()
        status, payload = runner.run(
            function_path="component.observe.understand_current_screen",
            kwargs={"query": "test"},
            allowed_control_modules=["decide"],
            allowed_control_components=[],
            allowed_control_functions=[],
            allowed_toolsets=[],
        )
        self.assertEqual(status, "failed")
        self.assertIn("未授权", str(payload.get("error") or ""))

    def test_tool_runner_should_block_disabled_component_function(self):
        runner = ToolRunner()
        with patch.object(
            runner.component_tool,
            "control_call",
            return_value={
                "success": True,
                "data": {
                    "result": [
                        {
                            "module": "observe",
                            "enabled": False,
                            "functions": ["component.observe.understand_current_screen"],
                        }
                    ]
                },
            },
        ):
            status, payload = runner.run(
                function_path="component.observe.understand_current_screen",
                kwargs={"query": "test"},
                allowed_control_modules=["observe"],
                allowed_control_components=[],
                allowed_control_functions=[],
                allowed_toolsets=[],
            )
        self.assertEqual(status, "failed")
        self.assertIn("已停用", str(payload.get("error") or ""))

    def test_tool_runner_should_build_safe_kwargs_for_decide_text_generation(self):
        safe_kwargs = ToolRunner._build_safe_kwargs(
            function_path="component.decide.text_generation",
            raw_kwargs={"query": "请分析当前页面"},
            model_id="qwen-plus",
        )
        self.assertEqual(safe_kwargs.get("model"), "qwen-plus")
        self.assertEqual(safe_kwargs.get("prompt"), "请分析当前页面")

    def test_tool_runner_should_resolve_module_from_function_path(self):
        runner = ToolRunner()
        module_name = runner._resolve_module_name("component.decide.create_qwen_client")
        self.assertEqual(module_name, "decide")

    def test_tool_runner_should_fail_when_create_directory_missing_dir_path(self):
        runner = ToolRunner()
        status, payload = runner.run(
            function_path="tools.file_path_tool.create_directory",
            kwargs={},
            allowed_control_modules=[],
            allowed_control_components=[],
            allowed_control_functions=[],
            allowed_toolsets=["file_path_tool"],
            model_id="qwen-plus",
        )
        self.assertEqual(status, "failed")
        self.assertIn("目录路径", str(payload.get("error") or ""))

    def test_tool_runner_should_fail_when_read_file_missing_file_path(self):
        runner = ToolRunner()
        status, payload = runner.run(
            function_path="tools.file_operator_tool.read_file",
            kwargs={},
            allowed_control_modules=[],
            allowed_control_components=[],
            allowed_control_functions=[],
            allowed_toolsets=["file_operator_tool"],
            model_id="qwen-plus",
        )
        self.assertEqual(status, "failed")
        self.assertIn("文件路径", str(payload.get("error") or ""))

    def test_tool_runner_should_preserve_explicit_dir_path_for_create_directory(self):
        safe_kwargs = ToolRunner._build_safe_kwargs(
            function_path="tools.file_path_tool.create_directory",
            raw_kwargs={"dir_path": "tmp/demo", "create_parent_dirs": False, "exist_ok": False},
            model_id="qwen-plus",
        )
        self.assertEqual(safe_kwargs.get("dir_path"), "tmp/demo")
        self.assertFalse(bool(safe_kwargs.get("create_parent_dirs")))
        self.assertFalse(bool(safe_kwargs.get("exist_ok")))

    def test_tool_runner_should_reject_non_direct_component_function(self):
        runner = ToolRunner()
        status, payload = runner.run(
            function_path="component.handle.run_macos_terminal_command",
            kwargs={"query": "执行命令"},
            allowed_control_modules=["handle"],
            allowed_control_components=[],
            allowed_control_functions=[],
            allowed_toolsets=[],
            model_id="qwen-plus",
        )
        self.assertEqual(status, "failed")
        self.assertTrue(bool(payload.get("replan_required")))
        self.assertIn("直调白名单", str(payload.get("error") or ""))

    def test_tool_runner_should_allow_cursor_cli_tool_function(self):
        runner = ToolRunner()
        with patch.object(
            runner.tool_proxy,
            "call_tool_function",
            return_value={"success": True, "data": {"output": "ok"}},
        ) as mock_call:
            status, payload = runner.run(
                function_path="tools.cursor_cli_tool.call_cursor_agent",
                kwargs={"object_id": "obj-1", "prompt": "hi"},
                allowed_control_modules=[],
                allowed_control_components=[],
                allowed_control_functions=[],
                allowed_toolsets=["cursor_cli_tool"],
                model_id="qwen-plus",
            )
        self.assertEqual(status, "success")
        self.assertEqual(payload.get("function_path"), "tools.cursor_cli_tool.call_cursor_agent")
        mock_call.assert_called_once()

    def test_tool_runner_should_allow_cursor_cli_create_session_function(self):
        runner = ToolRunner()
        with patch.object(
            runner.tool_proxy,
            "call_tool_function",
            return_value={"success": True, "data": {"object_id": "obj-1"}},
        ) as mock_call:
            status, payload = runner.run(
                function_path="tools.cursor_cli_tool.create_cursor_cli_session",
                kwargs={"cwd": "/tmp"},
                allowed_control_modules=[],
                allowed_control_components=[],
                allowed_control_functions=[],
                allowed_toolsets=["cursor_cli_tool"],
                model_id="qwen-plus",
            )
        self.assertEqual(status, "success")
        self.assertEqual(payload.get("function_path"), "tools.cursor_cli_tool.create_cursor_cli_session")
        mock_call.assert_called_once()

    def test_tool_runner_should_allow_macos_terminal_run_command_and_build_disk_command(self):
        runner = ToolRunner()
        with patch.object(
            runner.tool_proxy,
            "call_tool_function",
            return_value={"success": True, "data": {"stdout": "Filesystem ..."}},
        ) as mock_call:
            status, payload = runner.run(
                function_path="tools.macos_terminal_tool.run_command",
                kwargs={"query": "请查询当前磁盘剩余空间"},
                allowed_control_modules=[],
                allowed_control_components=[],
                allowed_control_functions=[],
                allowed_toolsets=["macos_terminal_tool"],
                model_id="qwen-plus",
            )
        self.assertEqual(status, "success")
        self.assertEqual(payload.get("function_path"), "tools.macos_terminal_tool.run_command")
        called_kwargs = mock_call.call_args.kwargs.get("kwargs") or {}
        self.assertEqual(called_kwargs.get("command"), "df -h / /System/Volumes/Data")

    def test_mindforge_runner_should_build_tools_from_component_list(self):
        raw_components = [
            {
                "module": "observe",
                "enabled": True,
                "functions": ["component.observe.understand_current_screen"],
            },
            {
                "module": "handle",
                "enabled": False,
                "functions": ["component.handle.get_system_info"],
            },
            {
                "module": "decide",
                "enabled": True,
                "functions": ["component.decide.text_generation"],
            },
        ]
        tools = MindforgeRunner._build_tools_from_component_list(
            raw_components=raw_components,
            allowed_modules={"observe", "handle"},
            allowed_components=set(),
            allowed_functions=set(),
            ranked_map={},
        )
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].function_path, "component.observe.understand_current_screen")
        self.assertEqual(tools[0].name, "observe_understand_current_screen")

    @patch("collector.orchestration.planner.search_component_functions")
    @patch("collector.orchestration.planner.analyzer.chat")
    def test_planner_should_prefer_search_result_tool_target(self, mock_chat, mock_search_component_functions):
        mock_chat.return_value = {"success": False, "response": "", "error": "planner llm unavailable"}
        mock_search_component_functions.return_value = (
            [{"path": "component.handle.get_system_info", "score": 0.92}],
            {"engine_used": "native"},
        )
        planner = CustomPlanner()
        plan = planner.build_plan(
            user_query="帮我查询系统信息",
            allowed_agent_modules=[],
            allowed_control_modules=["handle"],
            allowed_control_components=[],
            allowed_control_functions=[],
            capability_search_mode="hybrid",
        )
        tool_steps = [item for item in plan.steps if item.step_type == "tool"]
        self.assertEqual(len(tool_steps), 1)
        self.assertEqual(tool_steps[0].target, "component.handle.get_system_info")
        self.assertIsInstance(tool_steps[0].input.get("fallback_targets"), list)

    def test_mindforge_runner_should_sort_tools_by_rank(self):
        raw_components = [
            {
                "module": "observe",
                "enabled": True,
                "functions": [
                    "component.observe.capture_screen_to_file",
                    "component.observe.understand_current_screen",
                ],
            }
        ]
        ranked_map = {
            "component.observe.understand_current_screen": {
                "rank": 0,
                "score": 0.9,
                "description": "实时理解当前屏幕",
            },
            "component.observe.capture_screen_to_file": {
                "rank": 2,
                "score": 0.3,
                "description": "执行截图",
            },
        }
        tools = MindforgeRunner._build_tools_from_component_list(
            raw_components=raw_components,
            allowed_modules={"observe"},
            allowed_components=set(),
            allowed_functions=set(),
            ranked_map=ranked_map,
        )
        self.assertEqual(len(tools), 2)
        self.assertEqual(tools[0].function_path, "component.observe.understand_current_screen")
        self.assertEqual(tools[0].description, "实时理解当前屏幕")

    @patch("collector.orchestration.mindforge_runner.build_mindforge_strategy")
    @patch.object(MindforgeRunner, "_build_tools")
    def test_mindforge_runner_should_support_cot_without_tools(self, mock_build_tools, mock_build_strategy):
        class _DummyResult:
            success = True

            @staticmethod
            def to_dict():
                return {"success": True, "final_answer": "cot done", "steps": [], "error": ""}

        class _DummyStrategy:
            requires_tools = False

            @staticmethod
            def run(user_query, tools, config, system_prompt=""):
                return _DummyResult()

        mock_build_tools.return_value = []
        mock_build_strategy.return_value = _DummyStrategy()
        runner = MindforgeRunner()
        status, payload = runner.run(
            query="给我一个建议",
            model_id="qwen-plus",
            allowed_toolsets=[],
            allowed_control_modules=[],
            allowed_control_components=[],
            allowed_control_functions=[],
            strategy_name="cot",
        )
        self.assertEqual(status, "success")
        self.assertEqual(payload.get("final_answer"), "cot done")
        mock_build_tools.assert_not_called()

    @patch("collector.orchestration.mindforge_runner.build_mindforge_strategy")
    @patch.object(MindforgeRunner, "_build_tools")
    def test_mindforge_runner_should_build_tools_for_auto_tool_context(self, mock_build_tools, mock_build_strategy):
        class _DummyResult:
            success = True

            @staticmethod
            def to_dict():
                return {"success": True, "final_answer": "auto done", "steps": [], "error": ""}

        class _DummyStrategy:
            requires_tools = False
            wants_tool_context = True

            @staticmethod
            def run(user_query, tools, config, system_prompt=""):
                return _DummyResult()

        mock_build_tools.return_value = [
            ReActTool(
                name="run_terminal",
                function_path="component.handle.run_macos_terminal_command",
                description="执行终端命令",
            )
        ]
        mock_build_strategy.return_value = _DummyStrategy()
        runner = MindforgeRunner()
        status, payload = runner.run(
            query="查看目录",
            model_id="qwen-plus",
            allowed_toolsets=[],
            allowed_control_modules=["handle"],
            allowed_control_components=[],
            allowed_control_functions=[],
            strategy_name="auto",
        )
        self.assertEqual(status, "success")
        self.assertEqual(payload.get("final_answer"), "auto done")
        mock_build_tools.assert_called_once()

    @patch("collector.orchestration.mindforge_runner.build_mindforge_strategy")
    @patch.object(MindforgeRunner, "_build_tools")
    def test_mindforge_runner_should_force_react_when_cot_requested_for_execution_query(
        self,
        mock_build_tools,
        mock_build_strategy,
    ):
        class _DummyResult:
            success = True

            @staticmethod
            def to_dict():
                return {"success": True, "final_answer": "react done", "steps": [], "error": ""}

        class _DummyStrategy:
            requires_tools = True
            wants_tool_context = False

            @staticmethod
            def run(user_query, tools, config, system_prompt=""):
                return _DummyResult()

        mock_build_tools.return_value = [
            ReActTool(
                name="run_terminal",
                function_path="tools.macos_terminal_tool.run_command",
                description="执行终端命令",
            )
        ]
        mock_build_strategy.return_value = _DummyStrategy()
        runner = MindforgeRunner()
        status, payload = runner.run(
            query="请执行命令查询磁盘剩余空间",
            model_id="qwen-plus",
            allowed_toolsets=["macos_terminal_tool"],
            allowed_control_modules=[],
            allowed_control_components=[],
            allowed_control_functions=[],
            strategy_name="cot",
        )
        self.assertEqual(status, "success")
        self.assertEqual(payload.get("requested_strategy"), "cot")
        self.assertEqual(payload.get("effective_strategy"), "react")
        requested_names = [args[0][0] for args in mock_build_strategy.call_args_list]
        self.assertIn("cot", requested_names)
        self.assertIn("react", requested_names)

    def test_capability_search_should_preload_to_database_file(self):
        with tempfile.TemporaryDirectory(prefix="capability_search_") as tmp:
            engine = capability_search.CapabilitySearchEngine()
            engine.cache_path = Path(tmp) / "data" / "database" / "capability_callable_index.json"

            signature_holder = {"value": "sig-v1"}
            engine._compute_source_signature = lambda: signature_holder["value"]  # type: ignore[assignment]
            engine._build_agent_entries = lambda: []  # type: ignore[assignment]
            engine._build_tool_entries = lambda: []  # type: ignore[assignment]
            engine._build_component_entries = lambda: [  # type: ignore[assignment]
                {
                    "kind": "component_function",
                    "name": "get_system_info",
                    "path": "component.handle.get_system_info",
                    "module": "handle",
                    "description": "查询系统信息",
                    "search_text": "get_system_info component.handle.get_system_info 查询系统信息",
                    "tokens": {"system": 0.5, "info": 0.5},
                }
            ]

            result = engine.preload()
            self.assertTrue(result.get("success"))
            self.assertTrue(engine.cache_path.exists())

            persisted = json.loads(engine.cache_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted.get("source_signature"), "sig-v1")
            self.assertEqual(len(persisted.get("entries", [])), 1)

    def test_capability_search_should_keep_memory_and_disk_consistent_after_update(self):
        with tempfile.TemporaryDirectory(prefix="capability_search_") as tmp:
            engine = capability_search.CapabilitySearchEngine()
            engine.cache_path = Path(tmp) / "data" / "database" / "capability_callable_index.json"

            signature_holder = {"value": "sig-v1"}
            source_entries = {
                "sig-v1": [
                    {
                        "kind": "component_function",
                        "name": "get_system_info",
                        "path": "component.handle.get_system_info",
                        "module": "handle",
                        "description": "系统信息",
                        "search_text": "component.handle.get_system_info 系统信息",
                        "tokens": {"system": 1.0},
                    }
                ],
                "sig-v2": [
                    {
                        "kind": "component_function",
                        "name": "understand_current_screen",
                        "path": "component.observe.understand_current_screen",
                        "module": "observe",
                        "description": "屏幕理解",
                        "search_text": "component.observe.understand_current_screen 屏幕理解",
                        "tokens": {"screen": 1.0},
                    }
                ],
            }
            engine._compute_source_signature = lambda: signature_holder["value"]  # type: ignore[assignment]
            engine._build_agent_entries = lambda: []  # type: ignore[assignment]
            engine._build_tool_entries = lambda: []  # type: ignore[assignment]
            engine._build_component_entries = lambda: list(source_entries[signature_holder["value"]])  # type: ignore[assignment]

            engine.preload()
            signature_holder["value"] = "sig-v2"
            _ = engine.search(
                query="屏幕",
                search_mode="hybrid",
                kind_filter={"component_function"},
                allowed_control_modules={"observe"},
                top_k=5,
            )

            persisted = json.loads(engine.cache_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted.get("source_signature"), "sig-v2")
            self.assertEqual(engine._memory_signature, "sig-v2")
            self.assertEqual(persisted.get("entries", [])[0].get("path"), "component.observe.understand_current_screen")

    @patch("collector.orchestration.service.analyzer.chat")
    @patch("collector.orchestration.service.CustomPlanner.build_plan")
    def test_service_should_fallback_when_planner_raises(self, mock_build_plan, mock_chat):
        mock_build_plan.side_effect = RuntimeError("planner exploded")
        mock_chat.return_value = {"success": True, "response": "fallback answer", "error": ""}
        result = run_companion_orchestration(
            {
                "user_query": "你好",
                "model_id": "qwen-plus",
                "allowed_agent_modules": [],
                "allowed_control_modules": [],
            }
        )
        self.assertTrue(result.get("success"))
        self.assertTrue(result.get("fallback_used"))
        self.assertEqual(result.get("final_answer"), "fallback answer")

    @patch("collector.orchestration.service.analyzer.chat")
    @patch("collector.orchestration.service.CustomPlanner.build_plan")
    def test_service_should_keep_companion_anchor_in_fallback(self, mock_build_plan, mock_chat):
        mock_build_plan.side_effect = RuntimeError("planner exploded")
        mock_chat.return_value = {"success": True, "response": "fallback answer", "error": ""}
        result = run_companion_orchestration(
            {
                "user_query": "请继续",
                "model_id": "qwen-plus",
                "allowed_agent_modules": [],
                "allowed_control_modules": [],
                "system_prompt": "这是原始系统提示",
                "companion": {
                    "id": 1001,
                    "name": "dev_partner",
                    "display_name": "开发伙伴",
                    "role_title": "高级开发顾问",
                    "persona": "严格按项目规范推进并优先保证可执行结果",
                    "tone": "简洁直接",
                    "memory_notes": "长期关注代码可维护性与风险兜底",
                },
            }
        )
        self.assertTrue(result.get("success"))
        self.assertTrue(result.get("fallback_used"))
        self.assertEqual(result.get("final_answer"), "fallback answer")
        called_history = mock_chat.call_args.kwargs.get("conversation_history") or []
        self.assertGreaterEqual(len(called_history), 2)
        self.assertEqual(called_history[0].get("role"), "system")
        system_text = str(called_history[0].get("content") or "")
        self.assertIn("伙伴画像高优先级锚点", system_text)
        self.assertIn("角色描述：严格按项目规范推进并优先保证可执行结果", system_text)

    @patch("collector.orchestration.coordinator.analyzer.chat")
    def test_coordinator_should_run_summarize_when_dependency_failed(self, mock_chat):
        mock_chat.return_value = {"success": True, "response": "这是汇总结果", "error": ""}
        plan = ExecutionPlan.new_plan(goal="测试总结软依赖")
        plan.steps = [
            PlanStep(
                step_id="step_agent_mindforge",
                step_type="agent",
                target="mindforge",
                input={"query": "帮我分析问题"},
                depends_on=[],
            ),
            PlanStep(
                step_id="step_summarize",
                step_type="summarize",
                target="answer_synthesizer",
                input={"query": "帮我分析问题"},
                depends_on=["step_agent_mindforge"],
            ),
        ]
        coordinator = Coordinator()
        result = coordinator.run_plan(
            plan=plan,
            runtime_context={
                "user_query": "帮我分析问题",
                "model_id": "qwen-plus",
                "allowed_agent_modules": [],
                "allowed_control_modules": [],
            },
        ).to_dict()
        by_step = {item.get("step_id"): item for item in result.get("step_results", [])}
        self.assertEqual(by_step["step_agent_mindforge"]["status"], "failed")
        self.assertEqual(by_step["step_summarize"]["status"], "success")
        self.assertEqual(result.get("final_answer"), "这是汇总结果")

    @patch("collector.orchestration.coordinator.analyzer.chat")
    @patch.object(MindforgeRunner, "run")
    def test_coordinator_should_replan_after_summarize_signal_when_incomplete(
        self,
        mock_mindforge_run,
        mock_chat,
    ):
        mock_chat.side_effect = [
            {
                "success": True,
                "response": "已识别系统环境，但未获取磁盘剩余空间，当前任务未完成；建议执行 df -h 查询。",
                "error": "",
            },
            {
                "success": True,
                "response": '{"need_replan":true,"has_alternative":true,"reason":"缺少关键观测结果","alternative_plan":"调用终端执行 df -h 查询磁盘剩余空间"}',
                "error": "",
            },
        ]
        mock_mindforge_run.return_value = ("success", {"final_answer": "当前磁盘可用空间为 128GiB"})
        plan = ExecutionPlan.new_plan(goal="总结后重规划")
        plan.steps = [
            PlanStep(
                step_id="step_summarize",
                step_type="summarize",
                target="answer_synthesizer",
                input={"query": "查看当前磁盘剩余空间"},
                depends_on=[],
            )
        ]
        coordinator = Coordinator()
        result = coordinator.run_plan(
            plan=plan,
            runtime_context={
                "user_query": "查看当前磁盘剩余空间",
                "model_id": "qwen-plus",
                "allowed_agent_modules": ["mindforge"],
                "allowed_control_modules": ["handle"],
                "allowed_control_components": [],
                "allowed_control_functions": [],
                "allowed_toolsets": [],
            },
        ).to_dict()
        by_step = {item.get("step_id"): item for item in result.get("step_results", [])}
        self.assertEqual(by_step["step_summarize"]["status"], "success")
        self.assertIn("step_summarize_replan_mindforge", by_step)
        self.assertEqual(by_step["step_summarize_replan_mindforge"]["status"], "success")
        summarize_output = by_step["step_summarize"]["output"] or {}
        completion_signal = summarize_output.get("completion_signal") or {}
        self.assertTrue(bool(completion_signal.get("need_replan")))
        self.assertTrue(bool(completion_signal.get("has_alternative")))
        self.assertEqual(result.get("final_answer"), "当前磁盘可用空间为 128GiB")
        self.assertTrue(mock_mindforge_run.called)

    @patch("collector.orchestration.coordinator.Coordinator._analyze_summarize_replan_signal")
    @patch("collector.orchestration.coordinator.analyzer.chat")
    def test_coordinator_should_skip_completion_signal_when_disabled(self, mock_chat, mock_signal):
        mock_chat.return_value = {"success": True, "response": "查询完成：磁盘可用 120GiB", "error": ""}
        mock_signal.side_effect = AssertionError("should not call completion signal analyzer")
        plan = ExecutionPlan.new_plan(goal="跳过完成度信号")
        plan.steps = [
            PlanStep(
                step_id="step_summarize",
                step_type="summarize",
                target="answer_synthesizer",
                input={"query": "查询磁盘空间", "enable_completion_signal": False},
                depends_on=[],
            )
        ]
        coordinator = Coordinator()
        result = coordinator.run_plan(
            plan=plan,
            runtime_context={
                "user_query": "查询磁盘空间",
                "model_id": "qwen-plus",
                "allowed_agent_modules": ["mindforge"],
                "allowed_control_modules": [],
            },
        ).to_dict()
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("final_answer"), "查询完成：磁盘可用 120GiB")
        self.assertFalse(mock_signal.called)

    @patch("collector.orchestration.coordinator.analyzer.chat")
    @patch.object(MindforgeRunner, "run")
    @patch.object(ToolRunner, "run")
    def test_coordinator_should_trigger_mindforge_replan_when_tool_failed(
        self,
        mock_tool_run,
        mock_mindforge_run,
        mock_chat,
    ):
        mock_chat.return_value = {"success": True, "response": "汇总已完成", "error": ""}
        mock_tool_run.return_value = (
            "failed",
            {"error": "run_macos_terminal_command() missing 2 required positional arguments: 'session_id' and 'command'"},
        )
        mock_mindforge_run.return_value = ("success", {"final_answer": "通过重规划完成"})
        plan = ExecutionPlan.new_plan(goal="工具失败后切换")
        plan.steps = [
            PlanStep(
                step_id="step_tool_component",
                step_type="tool",
                target="component.handle.run_macos_terminal_command",
                input={
                    "query": "分析当前页面",
                    "fallback_targets": ["component.handle.get_system_info"],
                },
                depends_on=[],
            ),
            PlanStep(
                step_id="step_summarize",
                step_type="summarize",
                target="answer_synthesizer",
                input={"query": "分析当前页面"},
                depends_on=["step_tool_component"],
            ),
        ]
        coordinator = Coordinator()
        result = coordinator.run_plan(
            plan=plan,
            runtime_context={
                "user_query": "分析当前页面",
                "model_id": "qwen-plus",
                "allowed_agent_modules": ["mindforge"],
                "allowed_control_modules": ["observe", "handle"],
                "allowed_control_components": [],
                "allowed_control_functions": [],
                "allowed_toolsets": [],
            },
        ).to_dict()
        by_step = {item.get("step_id"): item for item in result.get("step_results", [])}
        self.assertEqual(by_step["step_tool_component"]["status"], "failed")
        tool_output = by_step["step_tool_component"]["output"] or {}
        self.assertEqual(tool_output.get("selected_function_path"), "component.handle.get_system_info")
        self.assertEqual(int(tool_output.get("attempt_count") or 0), 2)
        self.assertTrue(bool(tool_output.get("fallback_used")))
        self.assertIn("step_tool_component_replan_mindforge", by_step)
        self.assertEqual(by_step["step_tool_component_replan_mindforge"]["status"], "success")
        self.assertEqual(len(result.get("tool_events", [])), 3)

    @patch("collector.orchestration.coordinator.analyzer.chat")
    @patch.object(MindforgeRunner, "run")
    @patch.object(ToolRunner, "run")
    def test_coordinator_should_stop_retry_when_error_is_unauthorized(
        self,
        mock_tool_run,
        mock_mindforge_run,
        mock_chat,
    ):
        mock_chat.return_value = {"success": True, "response": "汇总已完成", "error": ""}
        mock_tool_run.return_value = ("failed", {"error": "工具模块未授权：decide"})
        mock_mindforge_run.return_value = ("failed", {"error": "mindforge 重规划失败"})
        plan = ExecutionPlan.new_plan(goal="未授权应立即停止")
        plan.steps = [
            PlanStep(
                step_id="step_tool_component",
                step_type="tool",
                target="component.decide.create_qwen_client",
                input={
                    "query": "初始化客户端",
                    "fallback_targets": [
                        "component.decide.text_generation",
                        "component.handle.get_system_info",
                    ],
                },
                depends_on=[],
            )
        ]
        coordinator = Coordinator()
        result = coordinator.run_plan(
            plan=plan,
            runtime_context={
                "user_query": "初始化客户端",
                "model_id": "qwen-plus",
                "allowed_agent_modules": ["mindforge"],
                "allowed_control_modules": ["decide", "handle"],
                "allowed_control_components": [],
                "allowed_control_functions": [],
                "allowed_toolsets": [],
            },
        ).to_dict()
        by_step = {item.get("step_id"): item for item in result.get("step_results", [])}
        tool_output = by_step["step_tool_component"]["output"] or {}
        self.assertEqual(by_step["step_tool_component"]["status"], "failed")
        self.assertEqual(int(tool_output.get("attempt_count") or 0), 1)
        self.assertIn("step_tool_component_replan_mindforge", by_step)
        self.assertEqual(len(result.get("tool_events", [])), 2)
        self.assertFalse(bool(tool_output.get("fallback_used")))

    def test_coordinator_should_try_fallback_tool_before_replan(self):
        coordinator = Coordinator()
        plan = ExecutionPlan.new_plan(goal="工具回退重试")
        plan.steps = [
            PlanStep(
                step_id="step_tool_component",
                step_type="tool",
                target="component.decide.text_generation",
                input={
                    "query": "请分析",
                    "fallback_targets": [
                        "component.handle.get_system_info",
                        "component.observe.understand_current_screen",
                    ],
                },
                depends_on=[],
            )
        ]
        with patch.object(
            ToolRunner,
            "run",
            side_effect=[
                ("failed", {"error": "timeout"}),
                ("success", {"result": {"ok": True}}),
            ],
        ) as mock_tool_run:
            result = coordinator.run_plan(
                plan=plan,
                runtime_context={
                    "user_query": "请分析",
                    "model_id": "qwen-plus",
                    "allowed_agent_modules": [],
                    "allowed_control_modules": ["decide", "handle", "observe"],
                    "allowed_control_components": [],
                    "allowed_control_functions": [],
                    "allowed_toolsets": [],
                },
            ).to_dict()
        by_step = {item.get("step_id"): item for item in result.get("step_results", [])}
        tool_output = by_step["step_tool_component"]["output"] or {}
        self.assertEqual(by_step["step_tool_component"]["status"], "success")
        self.assertEqual(int(tool_output.get("attempt_count") or 0), 2)
        self.assertTrue(bool(tool_output.get("fallback_used")))
        self.assertEqual(tool_output.get("selected_function_path"), "component.handle.get_system_info")
        self.assertEqual(mock_tool_run.call_count, 2)

    def test_mindforge_runner_should_use_dynamic_config_for_complex_query(self):
        config = MindforgeRunner._build_engine_config(
            query="请先分析当前页面，再读取系统信息，然后分步骤给出执行建议并说明失败兜底方案",
            model_id="qwen-plus",
            strategy_name="auto",
            tool_count=16,
        )
        self.assertGreaterEqual(int(config.max_steps), 7)
        self.assertGreaterEqual(int(config.max_tokens), 1200)


if __name__ == "__main__":
    unittest.main()

