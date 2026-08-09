from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from code_agent.core.models import (
    ActionType,
    AgentDecision,
    Budget,
    SubAgentRole,
    SubTaskSpec,
    ToolAction,
)


class MockScenarioError(ValueError):
    """Raised when a Mock LLM scenario cannot be loaded safely."""


class _StrictToolAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class _StrictBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iterations: int = 2
    seconds: int = 300
    tool_calls: int = 12
    llm_calls: int = 4


class _StrictSubTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: SubAgentRole
    goal: str
    path_scope: list[str] = Field(default_factory=list)
    budget: _StrictBudget = Field(default_factory=_StrictBudget)
    parent_depth: int = 0


class _StrictDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ActionType
    rationale: str = ""
    tool_action: _StrictToolAction | None = None
    subtask: _StrictSubTask | None = None
    completion_message: str | None = None


class _StrictScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[_StrictDecision]


def load_mock_decisions(path: Path) -> list[AgentDecision]:
    """Load a strict JSON scenario and return domain decisions in order."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        scenario = _StrictScenario.model_validate(raw)
        return [_to_agent_decision(decision) for decision in scenario.decisions]
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise MockScenarioError(str(exc)) from exc


def _to_agent_decision(decision: _StrictDecision) -> AgentDecision:
    tool_action = (
        ToolAction(tool=decision.tool_action.tool, arguments=decision.tool_action.arguments)
        if decision.tool_action
        else None
    )
    subtask = None
    if decision.subtask:
        subtask = SubTaskSpec(
            role=decision.subtask.role,
            goal=decision.subtask.goal,
            path_scope=decision.subtask.path_scope,
            budget=Budget(**decision.subtask.budget.model_dump()),
            parent_depth=decision.subtask.parent_depth,
        )
    return AgentDecision(
        action=decision.action,
        rationale=decision.rationale,
        tool_action=tool_action,
        subtask=subtask,
        completion_message=decision.completion_message,
    )
