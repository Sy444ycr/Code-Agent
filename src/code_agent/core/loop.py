from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from code_agent.core.context import ContextBuilder
from code_agent.core.events import Event
from code_agent.core.feedback import FeedbackAdapter
from code_agent.core.hooks import HookPoint, HookRunner
from code_agent.core.llm import LLMProvider
from code_agent.core.memory import InMemoryMemoryStore
from code_agent.core.models import (
    ActionType,
    ApprovalResolution,
    FeedbackSignal,
    LoopSpec,
    Task,
    TaskStatus,
    ToolAction,
)
from code_agent.core.policy import PolicyDecision, PolicyEngine
from code_agent.core.tools import ToolExecutor
from code_agent.core.workspace import Workspace


class TaskRunResult(BaseModel):
    status: TaskStatus
    feedback: list[FeedbackSignal] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    report: str = ""
    changed_files: list[str] = Field(default_factory=list)
    verification: list[dict[str, Any]] = Field(default_factory=list)


ApprovalHandler = Callable[[Task, ToolAction, PolicyDecision], ApprovalResolution]
EventCallback = Callable[[Event], None]
CancelCheck = Callable[[], bool]


class LoopController:
    def __init__(
        self,
        provider: LLMProvider,
        policy: PolicyEngine,
        tools: ToolExecutor,
        feedback: FeedbackAdapter,
        context: ContextBuilder | None = None,
        hooks: HookRunner | None = None,
        approval_handler: ApprovalHandler | None = None,
        event_callback: EventCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> None:
        self.provider = provider
        self.policy = policy
        self.tools = tools
        self.feedback = feedback
        self.context = context or ContextBuilder(InMemoryMemoryStore())
        self.hooks = hooks or HookRunner()
        self.approval_handler = approval_handler
        self.event_callback = event_callback
        self.cancel_check = cancel_check

    def run(self, task: Task, loop_spec: LoopSpec) -> TaskRunResult:
        signals: list[FeedbackSignal] = []
        events: list[Event] = []
        temporary_grants: set[str] = set()
        changed_files: list[str] = []
        verification: list[dict[str, Any]] = []
        sequence = 0

        def emit(kind: str, payload: dict[str, Any]) -> None:
            nonlocal sequence
            sequence += 1
            events.append(
                event := Event(
                    id=str(uuid4()), task_id=task.id, sequence=sequence, type=kind, payload=payload
                )
            )
            if self.event_callback is not None:
                self.event_callback(event)

        def finish(status: TaskStatus, report: str) -> TaskRunResult:
            return TaskRunResult(
                status=status,
                feedback=signals,
                events=events,
                report=report,
                changed_files=changed_files,
                verification=verification,
            )

        emit("task_started", {})
        self.hooks.run(HookPoint.ON_TASK_START, {"task": task})
        for _ in range(loop_spec.iteration_budget):
            if self.cancel_check is not None and self.cancel_check():
                return finish(TaskStatus.CANCELLED, "task cancelled")
            context = self.context.build(task, loop_spec, signals[-5:])
            decision = self.provider.decide(context)
            emit("decision_made", {"action": decision.action.value})
            if decision.action == ActionType.TOOL_CALL and decision.tool_action:
                policy = self.policy.evaluate(
                    decision.tool_action, task.mode, temporary_grants=temporary_grants
                )
                if policy.outcome == "deny":
                    return finish(TaskStatus.NEEDS_REVIEW, policy.reason)
                if policy.outcome == "ask":
                    emit(
                        "approval_requested",
                        {
                            "tool": decision.tool_action.tool,
                            "risk": policy.risk.value,
                            "reason": policy.reason,
                        },
                    )
                    if self.approval_handler is None:
                        return finish(TaskStatus.NEEDS_REVIEW, policy.reason)
                    resolution = self.approval_handler(task, decision.tool_action, policy)
                    emit(
                        "approval_decided",
                        {"approved": resolution.approved, "scope": resolution.scope},
                    )
                    if not resolution.approved:
                        if self.cancel_check is not None and self.cancel_check():
                            return finish(TaskStatus.CANCELLED, "task cancelled")
                        return finish(TaskStatus.NEEDS_REVIEW, "action rejected by user")
                    if resolution.scope == "task":
                        temporary_grants.add(policy.risk.value)
                result = self.tools.execute(decision.tool_action, self._workspace(task))
                if self.cancel_check is not None and self.cancel_check():
                    return finish(TaskStatus.CANCELLED, "task cancelled")
                changed_files.extend(result.changed_files)
                signal = self.feedback.from_tool_result(result)
                signals.append(signal)
                emit(
                    "feedback",
                    {
                        "status": signal.status.value,
                        "summary": signal.summary,
                        "changed_files": result.changed_files,
                    },
                )
                continue
            if decision.action == ActionType.COMPLETE:
                checks_ok = True
                for command in loop_spec.acceptance_checks:
                    check = self.tools.execute(
                        ToolAction(tool="run_check", arguments={"command": command}),
                        self._workspace(task),
                    )
                    verification.append(
                        {
                            "command": command,
                            "exit_code": check.exit_code,
                            "stdout": check.stdout,
                            "stderr": check.stderr,
                        }
                    )
                    checks_ok = checks_ok and check.exit_code == 0
                hook = self.hooks.run(HookPoint.BEFORE_TASK_COMPLETE, {"status": "succeeded"})
                if checks_ok and not hook.blocked:
                    return finish(TaskStatus.SUCCEEDED, decision.completion_message or "succeeded")
                return finish(TaskStatus.NEEDS_REVIEW, "acceptance checks did not pass")
            if decision.action == ActionType.STOP:
                return finish(TaskStatus.BLOCKED, decision.rationale)
        return finish(TaskStatus.BUDGET_EXHAUSTED, "iteration budget exhausted")

    @staticmethod
    def _workspace(task: Task) -> Workspace:
        return Workspace(Path(task.workspace))
