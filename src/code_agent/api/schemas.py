from __future__ import annotations

from pydantic import BaseModel, Field

from code_agent.core.models import AgentDecision, PermissionMode


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
