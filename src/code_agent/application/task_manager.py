from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Condition, Event, RLock
from typing import Literal
from uuid import uuid4

from code_agent.core.events import Event as TaskEvent
from code_agent.core.feedback import FeedbackAdapter
from code_agent.core.llm import MockLLMProvider
from code_agent.core.loop import LoopController, TaskRunResult
from code_agent.core.models import (
    AgentDecision,
    Approval,
    ApprovalResolution,
    LoopSpec,
    Task,
    TaskStatus,
    ToolAction,
)
from code_agent.core.policy import PolicyDecision, PolicyEngine
from code_agent.core.tools import ToolExecutor
from code_agent.storage import SQLiteStore


@dataclass
class _Runtime:
    task: Task
    cancel_event: Event = field(default_factory=Event)
    condition: Condition = field(default_factory=lambda: Condition(RLock()))
    approvals: dict[str, ApprovalResolution] = field(default_factory=dict)
    future: Future[TaskRunResult] | None = None


class TaskManager:
    """Coordinate in-process background task execution and API wakeups."""

    def __init__(self, store: SQLiteStore, max_workers: int = 4) -> None:
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._runtimes: dict[str, _Runtime] = {}
        self._lock = RLock()

    def submit(self, task: Task, loop_spec: LoopSpec, decisions: list[AgentDecision]) -> Task:
        with self._lock:
            if task.id in self._runtimes:
                raise ValueError(f"task {task.id} is already running")
            self.store.create_task(task, loop_spec)
            running = task.model_copy(update={"status": TaskStatus.RUNNING})
            self.store.update_task(running)
            runtime = _Runtime(task=running)
            self._runtimes[task.id] = runtime
            runtime.future = self.executor.submit(self._run, runtime, loop_spec, decisions)
        return running

    def get_task(self, task_id: str) -> Task | None:
        return self.store.get_task(task_id)

    def cancel(self, task_id: str) -> Task:
        runtime = self._runtime(task_id)
        task = self.store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status in _TERMINAL_STATES:
            raise ValueError(f"task {task_id} is terminal")
        runtime.cancel_event.set()
        with runtime.condition:
            runtime.condition.notify_all()
        return task

    def resume(self, task_id: str) -> Task:
        runtime = self._runtime(task_id)
        task = self.store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        if task.status != TaskStatus.WAITING_APPROVAL:
            raise ValueError(f"task {task_id} is not safely paused")
        if runtime.cancel_event.is_set():
            raise ValueError(f"task {task_id} is cancelled")
        return task

    def decide_approval(
        self,
        approval_id: str,
        approved: bool,
        scope: Literal["once", "task"],
        actor: str,
    ) -> Approval:
        approval = self.store.get_approval(approval_id)
        if approval is None:
            raise KeyError(approval_id)
        if approval.task_id is None:
            raise ValueError(f"approval {approval_id} is not attached to a task")
        runtime = self._runtime(approval.task_id)
        decided = self.store.decide_approval(approval_id, approved, scope, actor)
        with runtime.condition:
            runtime.approvals[approval_id] = ApprovalResolution(
                approved=approved, scope=scope
            )
            runtime.condition.notify_all()
        return decided

    def wait_for_event(self, task_id: str, after: int, timeout: float) -> None:
        runtime = self._runtime(task_id)
        with runtime.condition:
            runtime.condition.wait(timeout=timeout)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)

    def _runtime(self, task_id: str) -> _Runtime:
        with self._lock:
            runtime = self._runtimes.get(task_id)
        if runtime is None:
            raise KeyError(task_id)
        return runtime

    def _run(
        self, runtime: _Runtime, loop_spec: LoopSpec, decisions: list[AgentDecision]
    ) -> TaskRunResult:
        task = runtime.task

        def emit(event: TaskEvent) -> None:
            self.store.append_event(task.id, event.type, event.payload)
            with runtime.condition:
                runtime.condition.notify_all()

        def approval_handler(
            current_task: Task, action: ToolAction, policy: PolicyDecision
        ) -> ApprovalResolution:
            approval = self.store.save_approval(
                Approval(
                    task_id=current_task.id,
                    tool_call_id=str(uuid4()),
                    reason=policy.reason,
                )
            )
            self.store.update_task(
                current_task.model_copy(update={"status": TaskStatus.WAITING_APPROVAL})
            )
            with runtime.condition:
                while approval.id not in runtime.approvals and not runtime.cancel_event.is_set():
                    runtime.condition.wait(timeout=0.25)
                if runtime.cancel_event.is_set():
                    return ApprovalResolution(approved=False)
                return runtime.approvals[approval.id]

        try:
            loop = LoopController(
                provider=MockLLMProvider(decisions),
                policy=PolicyEngine(),
                tools=ToolExecutor(),
                feedback=FeedbackAdapter(),
                approval_handler=approval_handler,
                event_callback=emit,
                cancel_check=runtime.cancel_event.is_set,
            )
            result = loop.run(task, loop_spec)
        except Exception as exc:
            result = TaskRunResult(status=TaskStatus.FAILED, report=str(exc))
        final_task = task.model_copy(update={"status": result.status})
        self.store.update_task(final_task)
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
        with runtime.condition:
            runtime.condition.notify_all()
        return result


_TERMINAL_STATES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.NEEDS_REVIEW,
    TaskStatus.BLOCKED,
    TaskStatus.FAILED,
    TaskStatus.BUDGET_EXHAUSTED,
    TaskStatus.CANCELLED,
}
