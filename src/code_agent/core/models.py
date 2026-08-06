from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class PermissionMode(StrEnum):
    PLAN = "plan"
    SUPERVISED = "supervised"
    AUTO = "auto"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"
    FAILED = "failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"


class ActionType(StrEnum):
    TOOL_CALL = "tool_call"
    DISPATCH_SUBAGENT = "dispatch_subagent"
    REQUEST_USER_INPUT = "request_user_input"
    COMPLETE = "complete"
    STOP = "stop"


class RiskLevel(StrEnum):
    READ = "read"
    WRITE = "write"
    TEST = "test"
    SHELL = "shell"
    NETWORK = "network"
    INSTALL = "install"
    DELETE = "delete"
    GIT_WRITE = "git_write"
    FORBIDDEN = "forbidden"


class FeedbackStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    BLOCKED = "blocked"


class SubAgentRole(StrEnum):
    EXPLORER = "explorer"
    IMPLEMENTER = "implementer"
    VERIFIER = "verifier"
    REVIEWER = "reviewer"


class Budget(BaseModel):
    iterations: int = Field(default=8, ge=0)
    seconds: int = Field(default=1800, ge=0)
    tool_calls: int = Field(default=64, ge=0)
    llm_calls: int = Field(default=32, ge=0)


class LoopSpec(BaseModel):
    goal: str
    acceptance_checks: list[str] = Field(default_factory=list)
    iteration_budget: int = Field(default=8, ge=0)
    time_budget_seconds: int = Field(default=1800, ge=0)
    recovery_policy: dict[str, Any] = Field(default_factory=lambda: {"repeat_failure_limit": 2})
    human_gates: list[str] = Field(default_factory=list)
    terminal_states: list[TaskStatus] = Field(
        default_factory=lambda: [
            TaskStatus.SUCCEEDED,
            TaskStatus.NEEDS_REVIEW,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
            TaskStatus.BUDGET_EXHAUSTED,
            TaskStatus.CANCELLED,
        ]
    )


class ToolAction(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentDecision(BaseModel):
    action: ActionType
    rationale: str = ""
    tool_action: ToolAction | None = None
    subtask: SubTaskSpec | None = None
    completion_message: str | None = None

    @field_validator("tool_action")
    @classmethod
    def require_tool_for_tool_call(cls, value: ToolAction | None, info: Any) -> ToolAction | None:
        if info.data.get("action") == ActionType.TOOL_CALL and value is None:
            raise ValueError("tool_action is required for tool_call")
        return value


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace: str
    goal: str
    mode: PermissionMode = PermissionMode.SUPERVISED
    provider: str = "mock"
    status: TaskStatus = TaskStatus.PENDING
    budget: Budget = Field(default_factory=Budget)


class ToolResult(BaseModel):
    tool: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    changed_files: list[str] = Field(default_factory=list)


class FeedbackSignal(BaseModel):
    source: str
    status: FeedbackStatus
    summary: str
    evidence: list[str] = Field(default_factory=list)
    related_files: list[str] = Field(default_factory=list)
    fingerprint: str | None = None
    retryable: bool = True


class SubTaskSpec(BaseModel):
    role: SubAgentRole
    goal: str
    path_scope: list[str] = Field(default_factory=list)
    budget: Budget = Field(
        default_factory=lambda: Budget(iterations=2, seconds=300, tool_calls=12, llm_calls=4)
    )
    parent_depth: int = 0


class SubTaskResult(BaseModel):
    status: TaskStatus
    summary: str
    findings: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class Approval(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool_call_id: str
    status: Literal["pending", "approved", "rejected", "executed", "failed"] = "pending"
    scope: Literal["once", "task"] = "once"
    reason: str
    actor: str = "user"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
