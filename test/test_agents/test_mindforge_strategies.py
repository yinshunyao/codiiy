import os
import sys
import unittest
from unittest.mock import patch

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agents.mindforge.auto_strategy import AutoMindforgeStrategy
from agents.mindforge.cot_strategy import CoTMindforgeStrategy
from agents.mindforge.plan_execute_strategy import PlanExecuteMindforgeStrategy
from agents.mindforge.reflexion_strategy import ReflexionMindforgeStrategy
from agents.mindforge.react_strategy import (
    ReActEngineConfig,
    ReActRunResult,
    ReActStepRecord,
    ReActTool,
)
from agents.mindforge.strategy_factory import build_mindforge_strategy


class MindforgeStrategiesTestCase(unittest.TestCase):
    def setUp(self):
        self._auto_route_patcher = patch.object(
            AutoMindforgeStrategy,
            "_analyze_route_by_model",
            return_value=({}, "mock_route_disabled"),
        )
        self._auto_route_patcher.start()

    def tearDown(self):
        self._auto_route_patcher.stop()

    def test_factory_should_fallback_to_react_for_unknown_strategy(self):
        strategy = build_mindforge_strategy("unknown")
        self.assertEqual(strategy.name, "react")

    def test_factory_should_build_cot_strategy(self):
        strategy = build_mindforge_strategy("cot")
        self.assertEqual(strategy.name, "cot")
        self.assertFalse(strategy.requires_tools)

    def test_factory_should_build_auto_strategy(self):
        strategy = build_mindforge_strategy("auto")
        self.assertEqual(strategy.name, "auto")
        self.assertFalse(strategy.requires_tools)

    def test_factory_should_build_plan_execute_strategy(self):
        strategy = build_mindforge_strategy("plan_execute")
        self.assertEqual(strategy.name, "plan_execute")
        self.assertTrue(strategy.requires_tools)

    def test_factory_should_build_reflexion_strategy(self):
        strategy = build_mindforge_strategy("reflexion")
        self.assertEqual(strategy.name, "reflexion")
        self.assertTrue(strategy.requires_tools)

    def test_cot_strategy_should_return_final_answer(self):
        strategy = CoTMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus")
        tools = [
            ReActTool(
                name="read_file",
                function_path="component.handle.read_file",
                description="读取文件",
            )
        ]
        with patch.object(
            strategy.component_tool,
            "control_call",
            return_value={
                "success": True,
                "data": {
                    "result": {
                        "success": True,
                        "data": {
                            "choices": [
                                {
                                    "message": {
                                        "content": "这是 CoT 策略输出",
                                    }
                                }
                            ]
                        },
                    }
                },
            },
        ):
            result = strategy.run(
                user_query="请给出计划",
                tools=tools,
                config=config,
                system_prompt="你是助手",
            )
        self.assertTrue(result.success)
        self.assertEqual(result.final_answer, "这是 CoT 策略输出")
        self.assertEqual(len(result.steps), 1)

    @patch("agents.mindforge.plan_execute_strategy.api.ReActEngine.run")
    def test_plan_execute_strategy_should_plan_then_execute(self, mock_react_run):
        strategy = PlanExecuteMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus", max_steps=4)
        tools = [
            ReActTool(
                name="read_file",
                function_path="component.handle.read_file",
                description="读取文件",
            )
        ]
        mock_react_run.side_effect = [
            ReActRunResult(
                success=True,
                final_answer="已完成子任务1",
                steps=[ReActStepRecord(step=1, thought="执行步骤1")],
            ),
            ReActRunResult(
                success=True,
                final_answer="已完成子任务2",
                steps=[ReActStepRecord(step=1, thought="执行步骤2")],
            ),
        ]
        with patch.object(
            strategy.component_tool,
            "control_call",
            return_value={
                "success": True,
                "data": {
                    "result": {
                        "success": True,
                        "data": {
                            "choices": [
                                {
                                    "message": {
                                        "content": '{"plan":[{"task":"先读取文件"},{"task":"再总结结果"}]}',
                                    }
                                }
                            ]
                        },
                    }
                },
            },
        ):
            result = strategy.run(
                user_query="请读取文件并总结",
                tools=tools,
                config=config,
                system_prompt="你是助手",
            )
        self.assertTrue(result.success)
        self.assertIn("计划步骤", result.final_answer)
        self.assertEqual(len(result.steps), 2)
        self.assertIn("[plan_step 1/2]", result.steps[0].thought)
        self.assertIn("[plan_step 2/2]", result.steps[1].thought)

    @patch("agents.mindforge.reflexion_strategy.api.ReActEngine.run")
    def test_reflexion_strategy_should_retry_then_success(self, mock_react_run):
        strategy = ReflexionMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus", max_steps=4)
        tools = [
            ReActTool(
                name="read_file",
                function_path="component.handle.read_file",
                description="读取文件",
            )
        ]
        mock_react_run.side_effect = [
            ReActRunResult(
                success=False,
                error="第一次执行失败",
                steps=[ReActStepRecord(step=1, thought="尝试1")],
            ),
            ReActRunResult(
                success=True,
                final_answer="第二次执行成功",
                steps=[ReActStepRecord(step=1, thought="尝试2")],
            ),
        ]
        with patch.object(
            strategy.component_tool,
            "control_call",
            side_effect=[
                {
                    "success": True,
                    "data": {
                        "result": {
                            "success": True,
                            "data": {
                                "choices": [
                                    {
                                        "message": {
                                            "content": '{"success":false,"reason":"结果不满足目标","retry_advice":"补充关键参数后重试","retryable":true}',
                                        }
                                    }
                                ]
                            },
                        }
                    },
                },
                {
                    "success": True,
                    "data": {
                        "result": {
                            "success": True,
                            "data": {
                                "choices": [
                                    {
                                        "message": {
                                            "content": '{"success":true,"reason":"目标已达成","retry_advice":"","retryable":false}',
                                        }
                                    }
                                ]
                            },
                        }
                    },
                },
            ],
        ):
            result = strategy.run(
                user_query="请读取文件并总结",
                tools=tools,
                config=config,
                system_prompt="你是助手",
            )
        self.assertTrue(result.success)
        self.assertEqual(result.final_answer, "第二次执行成功")
        thoughts = [item.thought for item in result.steps]
        self.assertTrue(any("[reflexion attempt 1/3]" in text for text in thoughts))
        self.assertTrue(any("[reflexion attempt 2/3]" in text for text in thoughts))

    @patch("agents.mindforge.auto_strategy.api.PlanExecuteMindforgeStrategy.run")
    @patch("agents.mindforge.auto_strategy.api.ReflexionMindforgeStrategy.run")
    def test_auto_strategy_should_fallback_to_reflexion_after_plan_execute_failed(
        self,
        mock_reflexion_run,
        mock_plan_run,
    ):
        strategy = AutoMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus", max_steps=4)
        tools = [
            ReActTool(
                name="read_file",
                function_path="component.handle.read_file",
                description="读取文件",
            )
        ]
        mock_plan_run.return_value = ReActRunResult(success=False, error="plan failed", steps=[])
        mock_reflexion_run.return_value = ReActRunResult(
            success=True,
            final_answer="reflexion rescue done",
            steps=[
                ReActStepRecord(
                    step=1,
                    thought="retry done",
                    action={"tool": "read_file", "kwargs": {"path": "a.txt"}},
                    observation='{"ok": true}',
                )
            ],
        )

        result = strategy.run(
            user_query="请先分阶段执行，再逐步处理每一步，最后给总结",
            tools=tools,
            config=config,
            system_prompt="你是助手",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.final_answer, "reflexion rescue done")
        thoughts = [item.thought for item in result.steps]
        self.assertTrue(any("[auto route] choose_strategy" in text for text in thoughts))
        self.assertTrue(any("[auto stage plan_execute] failed" in text for text in thoughts))
        self.assertTrue(any("[auto stage reflexion attempt" in text for text in thoughts))

    @patch("agents.mindforge.auto_strategy.api.CoTMindforgeStrategy.run")
    def test_auto_strategy_should_choose_cot_when_no_tools(self, mock_cot_run):
        strategy = AutoMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus")
        mock_cot_run.return_value = ReActRunResult(
            success=True,
            final_answer="cot answer",
            steps=[ReActStepRecord(step=1, thought="cot single pass")],
        )
        result = strategy.run(
            user_query="请解释这个概念",
            tools=[],
            config=config,
            system_prompt="你是助手",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.final_answer, "cot answer")
        thoughts = [item.thought for item in result.steps]
        self.assertTrue(any("[auto route] choose_strategy" in text for text in thoughts))
        self.assertTrue(any("cot single pass" in text for text in thoughts))

    @patch("agents.mindforge.auto_strategy.api.CoTMindforgeStrategy.run")
    @patch("agents.mindforge.auto_strategy.api.ReActMindforgeStrategy.run")
    def test_auto_strategy_should_choose_react_for_action_with_general_tool_chain(
        self,
        mock_react_run,
        mock_cot_run,
    ):
        strategy = AutoMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus")
        tools = [
            ReActTool(
                name="run_terminal",
                function_path="component.handle.run_macos_terminal_command",
                description="执行终端命令",
            )
        ]
        mock_react_run.return_value = ReActRunResult(
            success=True,
            final_answer="已执行 ls -la",
            steps=[
                ReActStepRecord(
                    step=1,
                    thought="react execute",
                    action={"tool": "run_terminal", "kwargs": {"command": "ls -la"}},
                    observation='{"stdout":"ok"}',
                )
            ],
        )
        result = strategy.run(
            user_query="请查看当前目录",
            tools=tools,
            config=config,
            system_prompt="你是助手",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.final_answer, "已执行 ls -la")
        self.assertTrue(mock_react_run.called)
        self.assertFalse(mock_cot_run.called)

    @patch("agents.mindforge.auto_strategy.api.PlanExecuteMindforgeStrategy.run")
    @patch("agents.mindforge.auto_strategy.api.ReflexionMindforgeStrategy.run")
    @patch("agents.mindforge.auto_strategy.api.ReActMindforgeStrategy.run")
    def test_auto_strategy_should_fallback_chain_without_dead_end(
        self,
        mock_react_run,
        mock_reflexion_run,
        mock_plan_run,
    ):
        strategy = AutoMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus")
        tools = [
            ReActTool(
                name="run_terminal",
                function_path="component.handle.run_macos_terminal_command",
                description="执行终端命令",
            )
        ]
        mock_react_run.return_value = ReActRunResult(success=False, error="react failed", steps=[])
        mock_plan_run.return_value = ReActRunResult(
            success=True,
            final_answer="plan execute success",
            steps=[
                ReActStepRecord(
                    step=1,
                    thought="plan execute done",
                    action={"tool": "run_terminal", "kwargs": {"command": "echo ok"}},
                    observation='{"stdout":"ok"}',
                )
            ],
        )
        mock_reflexion_run.return_value = ReActRunResult(success=False, error="should not run", steps=[])
        result = strategy.run(
            user_query="请执行命令并输出结果",
            tools=tools,
            config=config,
            system_prompt="你是助手",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.final_answer, "plan execute success")
        self.assertTrue(mock_react_run.called)
        self.assertTrue(mock_plan_run.called)

    @patch("agents.mindforge.auto_strategy.api.CoTMindforgeStrategy.run")
    @patch("agents.mindforge.auto_strategy.api.ReflexionMindforgeStrategy.run")
    @patch("agents.mindforge.auto_strategy.api.PlanExecuteMindforgeStrategy.run")
    @patch("agents.mindforge.auto_strategy.api.ReActMindforgeStrategy.run")
    def test_auto_strategy_should_require_effective_execution_for_action_task(
        self,
        mock_react_run,
        mock_plan_run,
        mock_reflexion_run,
        mock_cot_run,
    ):
        strategy = AutoMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus")
        tools = [
            ReActTool(
                name="run_terminal",
                function_path="component.handle.run_macos_terminal_command",
                description="执行终端命令",
            )
        ]
        mock_react_run.return_value = ReActRunResult(success=False, error="react failed", steps=[])
        mock_plan_run.return_value = ReActRunResult(success=False, error="plan failed", steps=[])
        mock_reflexion_run.return_value = ReActRunResult(
            success=True,
            final_answer="建议下一步执行 df -h 查看磁盘剩余空间",
            steps=[ReActStepRecord(step=1, thought="只给建议，没有执行")],
        )
        mock_cot_run.return_value = ReActRunResult(
            success=True,
            final_answer="cot suggestion",
            steps=[ReActStepRecord(step=1, thought="cot single pass")],
        )

        result = strategy.run(
            user_query="请执行命令查看当前磁盘剩余空间并输出结果",
            tools=tools,
            config=config,
            system_prompt="你是助手",
        )
        self.assertFalse(result.success)
        self.assertIn("未形成有效工具执行闭环", result.error)
        self.assertTrue(mock_react_run.called)
        self.assertTrue(mock_plan_run.called)
        self.assertTrue(mock_reflexion_run.called)
        self.assertFalse(mock_cot_run.called)

    @patch("agents.mindforge.auto_strategy.api.ReActMindforgeStrategy.run")
    def test_auto_strategy_should_retry_same_stage_with_alternative_attempt(self, mock_react_run):
        strategy = AutoMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus")
        tools = [
            ReActTool(
                name="run_terminal",
                function_path="component.handle.run_macos_terminal_command",
                description="执行终端命令",
            )
        ]
        mock_react_run.side_effect = [
            ReActRunResult(success=False, error="first attempt failed", steps=[]),
            ReActRunResult(
                success=True,
                final_answer="second attempt success",
                steps=[
                    ReActStepRecord(
                        step=1,
                        thought="react execute",
                        action={"tool": "run_terminal", "kwargs": {"command": "df -h"}},
                        observation='{"stdout":"ok"}',
                    )
                ],
            ),
        ]
        result = strategy.run(
            user_query="请执行命令查看磁盘空间并返回结果",
            tools=tools,
            config=config,
            system_prompt="你是助手",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.final_answer, "second attempt success")
        self.assertEqual(mock_react_run.call_count, 2)
        thoughts = [item.thought for item in result.steps]
        self.assertTrue(any("[auto stage react] retry_alternative" in text for text in thoughts))

    @patch.object(AutoMindforgeStrategy, "_judge_stage_result_expectation")
    @patch("agents.mindforge.auto_strategy.api.PlanExecuteMindforgeStrategy.run")
    @patch("agents.mindforge.auto_strategy.api.ReActMindforgeStrategy.run")
    def test_auto_strategy_should_replan_when_success_result_not_expected(
        self,
        mock_react_run,
        mock_plan_run,
        mock_judge_outcome,
    ):
        strategy = AutoMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus")
        tools = [
            ReActTool(
                name="run_terminal",
                function_path="component.handle.run_macos_terminal_command",
                description="执行终端命令",
            )
        ]
        mock_react_run.side_effect = [
            ReActRunResult(
                success=True,
                final_answer="建议执行 df -h 查看磁盘剩余空间",
                steps=[
                    ReActStepRecord(
                        step=1,
                        thought="react execute 1",
                        action={"tool": "run_terminal", "kwargs": {"command": "df -h"}},
                        observation='{"stdout":"partial"}',
                    )
                ],
            ),
            ReActRunResult(
                success=True,
                final_answer="仍未返回最终可用空间",
                steps=[
                    ReActStepRecord(
                        step=1,
                        thought="react execute 2",
                        action={"tool": "run_terminal", "kwargs": {"command": "df -h /"}},
                        observation='{"stdout":"still partial"}',
                    )
                ],
            ),
        ]
        mock_plan_run.return_value = ReActRunResult(
            success=True,
            final_answer="当前磁盘可用空间为 128GiB",
            steps=[
                ReActStepRecord(
                    step=1,
                    thought="plan execute done",
                    action={"tool": "run_terminal", "kwargs": {"command": "df -h /System/Volumes/Data"}},
                    observation='{"stdout":"128GiB available"}',
                )
            ],
        )
        mock_judge_outcome.side_effect = [
            (False, "仅给出建议未完成结果交付", ""),
            (False, "输出仍缺少最终答案", ""),
            (True, "结果满足用户目标", ""),
        ]

        result = strategy.run(
            user_query="请执行命令查看当前磁盘剩余空间并输出结果",
            tools=tools,
            config=config,
            system_prompt="你是助手",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.final_answer, "当前磁盘可用空间为 128GiB")
        self.assertEqual(mock_react_run.call_count, 2)
        self.assertTrue(mock_plan_run.called)
        self.assertEqual(mock_judge_outcome.call_count, 3)
        thoughts = [item.thought for item in result.steps]
        self.assertTrue(any("[auto stage react] outcome_not_expected" in text for text in thoughts))

    def test_auto_strategy_should_extract_capability_tags_from_function_and_description(self):
        strategy = AutoMindforgeStrategy()
        tools = [
            ReActTool(
                name="run_terminal",
                function_path="component.handle.run_macos_terminal_command",
                description="执行终端命令并查看目录",
            ),
            ReActTool(
                name="http_fetch",
                function_path="component.handle.http_request",
                description="网络请求",
            ),
        ]
        caps = strategy._summarize_tools(tools=tools)
        tags = set(caps.get("capability_tags") or [])
        self.assertIn("command_exec", tags)
        self.assertIn("directory_browse", tags)
        self.assertIn("network_request", tags)

    @patch("agents.mindforge.auto_strategy.api.ReActMindforgeStrategy.run")
    def test_auto_strategy_should_explain_directory_route_by_command_exec_tag(self, mock_react_run):
        strategy = AutoMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus")
        tools = [
            ReActTool(
                name="run_terminal",
                function_path="component.handle.run_macos_terminal_command",
                description="执行终端命令",
            )
        ]
        mock_react_run.return_value = ReActRunResult(
            success=True,
            final_answer="ok",
            steps=[
                ReActStepRecord(
                    step=1,
                    thought="done",
                    action={"tool": "run_terminal", "kwargs": {"command": "pwd"}},
                    observation='{"stdout":"/tmp"}',
                )
            ],
        )
        result = strategy.run(
            user_query="查看当前目录并输出",
            tools=tools,
            config=config,
            system_prompt="你是助手",
        )
        self.assertTrue(result.success)
        self.assertTrue(any("command_exec" in str(item.observation or "") for item in result.steps))

    @patch("agents.mindforge.auto_strategy.api.PlanExecuteMindforgeStrategy.run")
    def test_auto_strategy_should_prefer_model_route_when_json_valid(self, mock_plan_run):
        strategy = AutoMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus")
        tools = [
            ReActTool(
                name="run_terminal",
                function_path="component.handle.run_macos_terminal_command",
                description="执行终端命令",
            )
        ]
        mock_plan_run.return_value = ReActRunResult(
            success=True,
            final_answer="model routed success",
            steps=[
                ReActStepRecord(
                    step=1,
                    thought="plan execute done",
                    action={"tool": "run_terminal", "kwargs": {"command": "echo ok"}},
                    observation='{"stdout":"ok"}',
                )
            ],
        )
        with patch.object(
            strategy,
            "_analyze_route_by_model",
            return_value=(
                {
                    "intent_type": "workflow",
                    "preferred_strategy": "plan_reflexion",
                    "must_execute": True,
                    "confidence": 0.92,
                    "reason": "任务包含多阶段执行目标",
                },
                "",
            ),
        ):
            result = strategy.run(
                user_query="请先读取目录再分析文件并输出结论",
                tools=tools,
                config=config,
                system_prompt="你是助手",
            )

        self.assertTrue(result.success)
        self.assertEqual(result.final_answer, "model routed success")
        self.assertTrue(any("source=model" in str(item.observation or "") for item in result.steps))

    @patch("agents.mindforge.auto_strategy.api.CoTMindforgeStrategy.run")
    @patch("agents.mindforge.auto_strategy.api.ReActMindforgeStrategy.run")
    def test_auto_strategy_should_force_react_when_model_route_returns_cot_for_execution_task(
        self,
        mock_react_run,
        mock_cot_run,
    ):
        strategy = AutoMindforgeStrategy()
        config = ReActEngineConfig(model="qwen-plus")
        tools = [
            ReActTool(
                name="run_terminal",
                function_path="tools.macos_terminal_tool.run_command",
                description="执行终端命令",
            )
        ]
        mock_react_run.return_value = ReActRunResult(
            success=True,
            final_answer="react executed",
            steps=[
                ReActStepRecord(
                    step=1,
                    thought="react done",
                    action={"tool": "run_terminal", "kwargs": {"command": "df -h / /System/Volumes/Data"}},
                    observation='{"stdout":"ok"}',
                )
            ],
        )
        with patch.object(
            strategy,
            "_analyze_route_by_model",
            return_value=(
                {
                    "intent_type": "qa",
                    "preferred_strategy": "cot",
                    "must_execute": False,
                    "confidence": 0.88,
                    "reason": "模型误判为问答",
                },
                "",
            ),
        ):
            result = strategy.run(
                user_query="请执行命令查看当前磁盘剩余空间并输出结果",
                tools=tools,
                config=config,
                system_prompt="你是助手",
            )
        self.assertTrue(result.success)
        self.assertEqual(result.final_answer, "react executed")
        self.assertTrue(mock_react_run.called)
        self.assertFalse(mock_cot_run.called)

    def test_reflexion_reflection_messages_should_include_system_prompt(self):
        messages = ReflexionMindforgeStrategy._build_reflection_messages(
            user_query="请执行任务",
            execute_result=ReActRunResult(success=False, error="执行失败", final_answer="", steps=[]),
            memory=type("Memory", (), {"to_prompt_text": lambda self: "1. 历史失败项"})(),
            tools=[],
            system_prompt="你是开发伙伴，必须坚持角色约束",
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("你是开发伙伴，必须坚持角色约束", messages[0]["content"])
        self.assertIn("Reflexion 反思器", messages[0]["content"])


if __name__ == "__main__":
    unittest.main()

