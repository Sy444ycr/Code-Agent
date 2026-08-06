from __future__ import annotations

from pydantic import BaseModel, Field

from code_agent.core.models import PermissionMode


class TaskCreate(BaseModel):
    workspace: str
    goal: str
    mode: PermissionMode = PermissionMode.SUPERVISED
    provider: str = "mock"
    acceptance_checks: list[str] = Field(default_factory=list)
