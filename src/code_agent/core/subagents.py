from __future__ import annotations

from collections.abc import Callable

from code_agent.core.models import SubAgentRole, SubTaskResult, SubTaskSpec, Task, TaskStatus


class SubAgentPolicyError(ValueError):
    pass


class SubAgentScheduler:
    def __init__(self, handler: Callable[[Task, SubTaskSpec], SubTaskResult] | None = None) -> None:
        self.handler = handler
        self.active_writers: set[str] = set()

    def dispatch(self, parent: Task, spec: SubTaskSpec) -> SubTaskResult:
        if spec.parent_depth >= 1:
            raise SubAgentPolicyError("subagent nesting depth cannot exceed one")
        for field in ("iterations", "seconds", "tool_calls", "llm_calls"):
            if getattr(spec.budget, field) > getattr(parent.budget, field):
                raise SubAgentPolicyError(f"child budget exceeds parent: {field}")
        if spec.role == SubAgentRole.IMPLEMENTER and parent.workspace in self.active_writers:
            raise SubAgentPolicyError("another writer is active in this workspace")
        if spec.role == SubAgentRole.IMPLEMENTER:
            self.active_writers.add(parent.workspace)
        try:
            if self.handler is None:
                return SubTaskResult(
                    status=TaskStatus.NEEDS_REVIEW, summary="no handler configured"
                )
            return self.handler(parent, spec)
        finally:
            self.active_writers.discard(parent.workspace)
