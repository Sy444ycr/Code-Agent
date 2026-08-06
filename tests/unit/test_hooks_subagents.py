import pytest

from code_agent.core.hooks import HookPoint, HookResult, HookRunner
from code_agent.core.models import (
    Budget,
    FeedbackStatus,
    PermissionMode,
    SubAgentRole,
    SubTaskResult,
    SubTaskSpec,
    Task,
    TaskStatus,
)
from code_agent.core.subagents import SubAgentPolicyError, SubAgentScheduler


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


def test_subagent_depth_cannot_exceed_one() -> None:
    with pytest.raises(SubAgentPolicyError):
        SubAgentScheduler().dispatch(
            Task(workspace="/repo", goal="parent", mode=PermissionMode.AUTO),
            SubTaskSpec(role=SubAgentRole.EXPLORER, goal="inspect", parent_depth=1),
        )


def test_subagent_budget_cannot_exceed_parent() -> None:
    parent = Task(
        workspace="/repo",
        goal="parent",
        budget=Budget(iterations=1, seconds=10, tool_calls=1, llm_calls=1),
    )
    spec = SubTaskSpec(
        role=SubAgentRole.VERIFIER,
        goal="verify",
        budget=Budget(iterations=2, seconds=20, tool_calls=2, llm_calls=2),
    )
    with pytest.raises(SubAgentPolicyError):
        SubAgentScheduler().dispatch(parent, spec)


def test_subagent_returns_structured_summary_only() -> None:
    scheduler = SubAgentScheduler(
        handler=lambda parent, spec: SubTaskResult(
            status=TaskStatus.NEEDS_REVIEW, summary="found files"
        )
    )
    result = scheduler.dispatch(
        Task(workspace="/repo", goal="parent"),
        SubTaskSpec(role=SubAgentRole.EXPLORER, goal="inspect"),
    )
    assert result.summary == "found files"
    assert not hasattr(result, "transcript")
