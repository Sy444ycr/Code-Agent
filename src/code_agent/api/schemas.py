from __future__ import annotations

from pydantic import BaseModel, Field

from code_agent.core.models import AgentDecision, Approval, LoopSpec, PermissionMode


class TaskCreate(BaseModel):
    workspace: str
    goal: str
    mode: PermissionMode = PermissionMode.SUPERVISED
    provider: str = "mock"
    mock_decisions: list[AgentDecision] = Field(default_factory=list)
    acceptance_checks: list[str] = Field(default_factory=list)


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    scope: str = "once"
    actor: str = "api-user"


class TaskSummaryResponse(BaseModel):
    id: str
    status: str
    workspace: str
    goal: str
    mode: str
    provider: str
    pending_approvals: list[Approval] = Field(default_factory=list)
    recovery_required: bool = False
    recovery_reason: str | None = None
    resumable: bool = False


class TaskDetailResponse(TaskSummaryResponse):
    loop_spec: LoopSpec | None = None
