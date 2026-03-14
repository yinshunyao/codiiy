import unittest

from agents.helm.requirement_session_command import RequirementSessionCommand


class RequirementSessionCommandTestCase(unittest.TestCase):
    def setUp(self):
        self.command = RequirementSessionCommand()

    def test_should_enter_organizing_when_collecting_and_confirmed_and_complete(self):
        decision = self.command.decide_transition(
            phase="collecting",
            user_content="我这边需求已经描述完了",
            analysis_is_complete=True,
        )
        self.assertTrue(decision.should_enter_organizing)
        self.assertFalse(decision.should_mark_completed)

    def test_should_not_enter_organizing_when_analysis_incomplete(self):
        decision = self.command.decide_transition(
            phase="collecting",
            user_content="需求清楚了",
            analysis_is_complete=False,
        )
        self.assertFalse(decision.should_enter_organizing)
        self.assertFalse(decision.should_mark_completed)

    def test_should_mark_completed_when_organizing_and_user_confirms(self):
        decision = self.command.decide_transition(
            phase="organizing",
            user_content="确认完成",
            analysis_is_complete=False,
        )
        self.assertFalse(decision.should_enter_organizing)
        self.assertTrue(decision.should_mark_completed)

    def test_custom_keywords_should_take_effect(self):
        command = RequirementSessionCommand(
            organize_confirm_keywords=("ok收集完成",),
            complete_confirm_keywords=("ok整理完成",),
        )
        collect_decision = command.decide_transition(
            phase="collecting",
            user_content="ok收集完成",
            analysis_is_complete=True,
        )
        complete_decision = command.decide_transition(
            phase="organizing",
            user_content="ok整理完成",
            analysis_is_complete=False,
        )
        self.assertTrue(collect_decision.should_enter_organizing)
        self.assertTrue(complete_decision.should_mark_completed)


if __name__ == "__main__":
    unittest.main()
