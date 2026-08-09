from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from code_agent.core.feedback import FeedbackAdapter
from code_agent.core.llm import MockLLMProvider
from code_agent.core.loop import LoopController, TaskRunResult
from code_agent.core.models import (
    AgentDecision,
    Approval,
    ApprovalResolution,
    LoopSpec,
    PermissionMode,
    Task,
    TaskStatus,
    ToolAction,
)
from code_agent.core.policy import PolicyDecision, PolicyEngine
from code_agent.core.tools import ToolExecutor
from code_agent.storage import SQLiteStore

ApprovalPrompt = Callable[[Task, ToolAction, PolicyDecision], ApprovalResolution]


class TaskService:
    """Run one local task and preserve its evidence in SQLite."""

    def __init__(self, store: SQLiteStore, approval_handler: ApprovalPrompt | None = None) -> None:
        self.store = store
        self.approval_handler = approval_handler

    def run(
        self,
        workspace: Path,
        goal: str,
        mode: PermissionMode,
        decisions: list[AgentDecision],
        acceptance_checks: list[str],
    ) -> TaskRunResult:
        resolved_workspace = workspace.resolve()
        if not resolved_workspace.is_dir():
            raise ValueError(f"workspace does not exist: {resolved_workspace}")
        task = Task(workspace=str(resolved_workspace), goal=goal, mode=mode, provider="mock")
        loop_spec = LoopSpec(goal=goal, acceptance_checks=acceptance_checks)
        self.store.create_task(task, loop_spec)
        running_task = task.model_copy(update={"status": TaskStatus.RUNNING})
        self.store.update_task(running_task)

        loop = LoopController(
            provider=MockLLMProvider(decisions),
            policy=PolicyEngine(),
            tools=ToolExecutor(),
            feedback=FeedbackAdapter(),
            approval_handler=self._approval_handler,
        )
        result = loop.run(running_task, loop_spec)
        for event in result.events:
            self.store.append_event(task.id, event.type, event.payload)
        completed_task = running_task.model_copy(update={"status": result.status})
        self.store.update_task(completed_task)
        self.store.append_event(
            task.id,
            "task_completed",
            {
                "status": result.status.value,
                "report": result.report,
                "changed_files": result.changed_files,
                "feedback": [signal.model_dump(mode="json") for signal in result.feedback],
                "verification": result.verification,
            },
        )
        return result

    def _approval_handler(
        self, task: Task, action: ToolAction, decision: PolicyDecision
    ) -> ApprovalResolution:
        approval = Approval(tool_call_id=str(uuid4()), reason=decision.reason)
        self.store.save_approval(approval)
        resolution = (
            self.approval_handler(task, action, decision)
            if self.approval_handler is not None
            else ApprovalResolution(approved=False)
        )
        self.store.save_approval(
            approval.model_copy(
                update={
                    "status": "approved" if resolution.approved else "rejected",
                    "scope": resolution.scope,
                }
            )
        )
        return resolution
