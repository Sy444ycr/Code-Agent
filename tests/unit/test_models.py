import pytest
from pydantic import ValidationError

from code_agent.core.models import (
    ActionType,
    AgentDecision,
    Budget,
    LoopSpec,
    PermissionMode,
    TaskStatus,
    ToolAction,
)


def test_loop_spec_requires_terminal_states() -> None:
    spec = LoopSpec(
        goal="修复失败测试",
        acceptance_checks=["pytest -q"],
        iteration_budget=3,
        time_budget_seconds=600,
    )

    assert spec.terminal_states == [
        TaskStatus.SUCCEEDED,
        TaskStatus.NEEDS_REVIEW,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.BUDGET_EXHAUSTED,
        TaskStatus.CANCELLED,
    ]


def test_agent_decision_validates_tool_call_arguments() -> None:
    decision = AgentDecision(
        action=ActionType.TOOL_CALL,
        rationale="read file",
        tool_action=ToolAction(tool="read_file", arguments={"path": "README.md"}),
    )

    assert decision.tool_action.tool == "read_file"


def test_negative_budget_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Budget(iterations=-1, seconds=10, tool_calls=1)


def test_permission_mode_values_are_stable() -> None:
    assert [mode.value for mode in PermissionMode] == ["plan", "supervised", "auto"]
