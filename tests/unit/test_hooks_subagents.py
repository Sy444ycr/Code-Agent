from code_agent.core.hooks import HookPoint, HookResult, HookRunner
from code_agent.core.models import FeedbackStatus


def test_before_task_complete_hook_can_block_success() -> None:
    runner = HookRunner()
    runner.register(
        HookPoint.BEFORE_TASK_COMPLETE,
        lambda payload: HookResult(blocked=True, message="missing checks"),
    )
    result = runner.run(HookPoint.BEFORE_TASK_COMPLETE, {"status": "succeeded"})
    assert result.blocked is True
    assert result.message == "missing checks"


def test_after_tool_call_hook_can_add_feedback() -> None:
    runner = HookRunner()
    runner.register(
        HookPoint.AFTER_TOOL_CALL,
        lambda payload: HookResult.feedback("hook", FeedbackStatus.FAILED, "custom failure"),
    )
    result = runner.run(HookPoint.AFTER_TOOL_CALL, {})
    assert result.feedback[0].source == "hook"
    assert result.feedback[0].summary == "custom failure"
