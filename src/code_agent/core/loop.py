from __future__ import annotations

from pathlib import Path
from collections.abc import Callable
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


ApprovalHandler = Callable[[Task, ToolAction, PolicyDecision], ApprovalResolution]


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
    ) -> None:
        self.provider = provider
        self.policy = policy
        self.tools = tools
        self.feedback = feedback
        self.context = context or ContextBuilder(InMemoryMemoryStore())
        self.hooks = hooks or HookRunner()
        self.approval_handler = approval_handler

    def run(self, task: Task, loop_spec: LoopSpec) -> TaskRunResult:
        signals: list[FeedbackSignal] = []
        events: list[Event] = []
        temporary_grants: set[str] = set()
        sequence = 0

        def emit(kind: str, payload: dict[str, Any]) -> None:
            nonlocal sequence
            sequence += 1
            events.append(
                Event(
                    id=str(uuid4()), task_id=task.id, sequence=sequence, type=kind, payload=payload
                )
            )

        emit("task_started", {})
        self.hooks.run(HookPoint.ON_TASK_START, {"task": task})
        for _ in range(loop_spec.iteration_budget):
            context = self.context.build(task, loop_spec, signals[-5:])
            decision = self.provider.decide(context)
            emit("decision_made", {"action": decision.action.value})
            if decision.action == ActionType.TOOL_CALL and decision.tool_action:
                policy = self.policy.evaluate(
                    decision.tool_action, task.mode, temporary_grants=temporary_grants
                )
                if policy.outcome == "deny":
                    return TaskRunResult(
                        status=TaskStatus.NEEDS_REVIEW,
                        feedback=signals,
                        events=events,
                        report=policy.reason,
                    )
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
                        return TaskRunResult(
                            status=TaskStatus.NEEDS_REVIEW,
                            feedback=signals,
                            events=events,
                            report=policy.reason,
                        )
                    resolution = self.approval_handler(task, decision.tool_action, policy)
                    emit(
                        "approval_decided",
                        {"approved": resolution.approved, "scope": resolution.scope},
                    )
                    if not resolution.approved:
                        return TaskRunResult(
                            status=TaskStatus.NEEDS_REVIEW,
                            feedback=signals,
                            events=events,
                            report="action rejected by user",
                        )
                    if resolution.scope == "task":
                        temporary_grants.add(policy.risk.value)
                result = self.tools.execute(decision.tool_action, self._workspace(task))
                signal = self.feedback.from_tool_result(result)
                signals.append(signal)
                emit("feedback", {"status": signal.status.value, "summary": signal.summary})
                continue
            if decision.action == ActionType.COMPLETE:
                checks_ok = all(
                    self.tools.execute(
                        ToolAction(tool="run_check", arguments={"command": command}),
                        self._workspace(task),
                    ).exit_code
                    == 0
                    for command in loop_spec.acceptance_checks
                )
                hook = self.hooks.run(HookPoint.BEFORE_TASK_COMPLETE, {"status": "succeeded"})
                if checks_ok and not hook.blocked:
                    return TaskRunResult(
                        status=TaskStatus.SUCCEEDED,
                        feedback=signals,
                        events=events,
                        report=decision.completion_message or "succeeded",
                    )
                return TaskRunResult(
                    status=TaskStatus.NEEDS_REVIEW,
                    feedback=signals,
                    events=events,
                    report="acceptance checks did not pass",
                )
            if decision.action == ActionType.STOP:
                return TaskRunResult(
                    status=TaskStatus.BLOCKED,
                    feedback=signals,
                    events=events,
                    report=decision.rationale,
                )
        return TaskRunResult(
            status=TaskStatus.BUDGET_EXHAUSTED,
            feedback=signals,
            events=events,
            report="iteration budget exhausted",
        )

    @staticmethod
    def _workspace(task: Task) -> Workspace:
        return Workspace(Path(task.workspace))
