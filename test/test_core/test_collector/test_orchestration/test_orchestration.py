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


class OrchestrationTestCase(unittest.TestCase):
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
        self.assertEqual(tool_output.get("selected_function_path"), "component.handle.run_macos_terminal_command")
        self.assertEqual(int(tool_output.get("attempt_count") or 0), 1)
        self.assertFalse(bool(tool_output.get("fallback_used")))
        self.assertIn("step_tool_component_replan_mindforge", by_step)
        self.assertEqual(by_step["step_tool_component_replan_mindforge"]["status"], "success")
        self.assertEqual(len(result.get("tool_events", [])), 2)

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


if __name__ == "__main__":
    unittest.main()

