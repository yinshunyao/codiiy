import os
import sys
import unittest
from unittest.mock import patch

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agents.mindforge.react_strategy import ReActEngine, ReActEngineConfig, ReActTool
from agents.mindforge.react_strategy.executor import ReActToolExecutor


class ReActEngineTestCase(unittest.TestCase):
    def _build_engine(self, max_steps: int = 3) -> ReActEngine:
        tools = [
            ReActTool(
                name="read_file",
                function_path="tools.file_operator_tool.read_file",
                description="读取文件内容",
            )
        ]
        config = ReActEngineConfig(max_steps=max_steps, use_langgraph_if_available=False)
        return ReActEngine(tools=tools, config=config)

    def test_run_completes_with_tool_then_done_signal(self):
        engine = self._build_engine(max_steps=3)
        model_outputs = [
            ('{"thought":"先读取文件","action":{"tool":"read_file","kwargs":{"path":"a.txt"}}}', "", {}),
            ('{"thought":"整理结果","done":true}', "", {}),
        ]

        with (
            patch.object(engine, "_call_reason_model", side_effect=model_outputs),
            patch.object(engine, "_execute_tool", return_value=('{"ok": true}', "")),
        ):
            result = engine.run("请读取 a.txt 并总结")

        self.assertTrue(result.success)
        self.assertIn("执行结果", result.final_answer)
        self.assertIn('"ok": true', result.final_answer)
        self.assertEqual(len(result.steps), 2)
        self.assertEqual(result.steps[0].action.get("tool"), "read_file")
        self.assertEqual(result.steps[0].observation, '{"ok": true}')

    def test_run_should_stop_when_parse_error_repeats(self):
        engine = self._build_engine(max_steps=2)
        with patch.object(engine, "_call_reason_model", return_value=("这不是 JSON", "", {})):
            result = engine.run("给我结果")

        self.assertFalse(result.success)
        self.assertIn("连续命中同类失败", result.error)
        self.assertEqual(len(result.steps), 2)
        self.assertIn("未找到有效 JSON 对象", result.steps[0].error)
        self.assertIn("未找到有效 JSON 对象", result.steps[1].error)

    def test_run_should_stop_on_unknown_tool_error(self):
        engine = self._build_engine(max_steps=2)
        model_outputs = [
            ('{"thought":"调用不存在工具","action":{"tool":"unknown_tool","kwargs":{}}}', "", {}),
            ('{"thought":"直接结束","done":true}', "", {}),
        ]

        with patch.object(engine, "_call_reason_model", side_effect=model_outputs):
            result = engine.run("执行一个未知工具")

        self.assertFalse(result.success)
        self.assertIn("不可恢复失败", result.error)
        self.assertEqual(len(result.steps), 1)
        self.assertEqual(result.steps[0].action.get("tool"), "unknown_tool")
        self.assertIn("工具未注册", result.steps[0].error)
        self.assertIn("未知工具", result.steps[0].observation)

    def test_run_supports_toolset_alias_tool_name(self):
        engine = self._build_engine(max_steps=3)
        model_outputs = [
            ('{"thought":"按模块别名调用","action":{"tool":"file_operator_tool","kwargs":{"path":"a.txt"}}}', "", {}),
            ('{"thought":"完成","done":true}', "", {}),
        ]
        with (
            patch.object(engine, "_call_reason_model", side_effect=model_outputs),
            patch.object(
                engine.executor.component_tool,
                "call_tool_function",
                return_value={"success": True, "data": {"result": {"ok": True}}},
            ) as mock_call,
        ):
            result = engine.run("读取文件")

        self.assertTrue(result.success)
        self.assertEqual(len(result.steps), 2)
        self.assertEqual(result.steps[0].action.get("tool"), "file_operator_tool")
        self.assertIn('"ok": true', result.steps[0].observation.lower())
        self.assertEqual(mock_call.call_count, 1)
        self.assertEqual(mock_call.call_args.kwargs.get("function_path"), "tools.file_operator_tool.read_file")

    def test_executor_returns_error_when_tool_alias_is_ambiguous(self):
        executor = ReActToolExecutor(
            tools=[
                ReActTool(
                    name="file_operator_tool_read_file",
                    function_path="tools.file_operator_tool.read_file",
                    description="读取文件",
                ),
                ReActTool(
                    name="file_operator_tool_write_file",
                    function_path="tools.file_operator_tool.write_file",
                    description="写入文件",
                ),
            ]
        )
        observation, error = executor.execute_tool(tool_name="file_operator_tool", kwargs={"path": "a.txt"})

        self.assertIn("未知工具", observation)
        self.assertIn("工具别名不唯一", error)

    def test_run_should_ignore_legacy_final_answer_and_use_observation(self):
        engine = self._build_engine(max_steps=3)
        model_outputs = [
            ('{"thought":"先读取文件","action":{"tool":"read_file","kwargs":{"path":"a.txt"}}}', "", {}),
            ('{"thought":"完成","final_answer":"这段文本不应直接作为最终回复"}', "", {}),
        ]
        with (
            patch.object(engine, "_call_reason_model", side_effect=model_outputs),
            patch.object(engine, "_execute_tool", return_value=('{"output": "文件内容A"}', "")),
        ):
            result = engine.run("读取文件")

        self.assertTrue(result.success)
        self.assertIn("文件内容A", result.final_answer)
        self.assertNotEqual(result.final_answer.strip(), "这段文本不应直接作为最终回复")

    def test_run_returns_error_when_user_query_is_empty(self):
        engine = self._build_engine(max_steps=1)
        result = engine.run("   ")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "user_query 不能为空")

    def test_run_should_stop_on_non_retryable_tool_error(self):
        engine = self._build_engine(max_steps=5)
        model_outputs = [
            ('{"thought":"创建目录","action":{"tool":"read_file","kwargs":{"path":"a"}}}', "", {}),
            ('{"thought":"重试一次","action":{"tool":"read_file","kwargs":{"path":"a"}}}', "", {}),
        ]
        with (
            patch.object(engine, "_call_reason_model", side_effect=model_outputs),
            patch.object(
                engine,
                "_execute_tool",
                return_value=(
                    '{"success":false,"error":"工具执行异常: TypeError: got an unexpected keyword argument \'path\'"}',
                    "工具执行异常: TypeError: got an unexpected keyword argument 'path'",
                ),
            ),
        ):
            result = engine.run("创建目录")

        self.assertFalse(result.success)
        self.assertIn("不可恢复失败", result.error)
        self.assertEqual(len(result.steps), 1)

    def test_run_should_stop_when_same_failure_repeats(self):
        engine = self._build_engine(max_steps=5)
        model_outputs = [
            ('{"thought":"尝试1","action":{"tool":"read_file","kwargs":{"path":"a.txt"}}}', "", {}),
            ('{"thought":"尝试2","action":{"tool":"read_file","kwargs":{"path":"a.txt"}}}', "", {}),
            ('{"thought":"尝试3","action":{"tool":"read_file","kwargs":{"path":"a.txt"}}}', "", {}),
        ]
        with (
            patch.object(engine, "_call_reason_model", side_effect=model_outputs),
            patch.object(
                engine,
                "_execute_tool",
                return_value=(
                    '{"success":false,"error":"执行失败: unknown runtime issue"}',
                    "执行失败: unknown runtime issue",
                ),
            ),
        ):
            result = engine.run("读取文件")

        self.assertFalse(result.success)
        self.assertIn("连续命中同类失败", result.error)
        self.assertEqual(len(result.steps), 2)


if __name__ == "__main__":
    unittest.main()
