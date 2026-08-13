import time
from threading import Barrier, Event, Lock, Thread

import pytest

from code_agent.application.task_manager import TaskManager
from code_agent.core.llm import MockLLMProvider, ProviderRequestError
from code_agent.core.models import (
    AgentDecision,
    Approval,
    LoopSpec,
    PermissionMode,
    Task,
    TaskRecovery,
    TaskStatus,
    ToolAction,
)
from code_agent.storage import SQLiteStore


def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not reached")


def test_submit_uses_injected_provider(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    manager = TaskManager(store)
    task = Task(workspace=str(tmp_path), goal="complete", mode=PermissionMode.PLAN)
    provider = MockLLMProvider([AgentDecision(action="complete", completion_message="done")])

    manager.submit(task, LoopSpec(goal="complete"), provider)
    wait_until(lambda: store.get_task(task.id).status == TaskStatus.SUCCEEDED)

    assert provider.contexts_seen
    manager.shutdown()


def test_submit_runs_in_background_and_persists_terminal_status(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    manager = TaskManager(store)
    task = Task(workspace=str(tmp_path), goal="complete", mode=PermissionMode.PLAN)
    spec = LoopSpec(goal="complete")

    manager.submit(
        task,
        spec,
        MockLLMProvider([AgentDecision(action="complete", completion_message="done")]),
    )
    wait_until(lambda: store.get_task(task.id).status == TaskStatus.SUCCEEDED)

    assert store.events_after(task.id, 0)[-1].type == "task_completed"
    manager.shutdown()


def test_submit_persists_recovery_before_starting_runtime(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    decisions = [AgentDecision(action="complete", completion_message="done")]
    recovery = TaskRecovery(mock_decisions=decisions)

    class InspectingManager(TaskManager):
        def __init__(self, store: SQLiteStore) -> None:
            super().__init__(store)
            self.recovery_seen: TaskRecovery | None = None

        def _start_runtime(self, task: Task, loop_spec: LoopSpec, provider) -> None:
            del loop_spec, provider
            self.recovery_seen = self.store.get_recovery(task.id)

    manager = InspectingManager(store)
    task = Task(workspace=str(tmp_path), goal="complete", mode=PermissionMode.PLAN)

    running = manager.submit(
        task,
        LoopSpec(goal="complete"),
        MockLLMProvider(decisions),
        recovery=recovery,
    )

    assert running.status == TaskStatus.RUNNING
    assert manager.recovery_seen == recovery
    assert store.get_recovery(task.id) == recovery
    manager.shutdown()


def test_api_approval_wakes_waiting_worker(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    manager = TaskManager(store)
    task = Task(workspace=str(tmp_path), goal="shell")
    spec = LoopSpec(goal="shell")
    manager.submit(
        task,
        spec,
        MockLLMProvider([
            AgentDecision(
                action="tool_call",
                tool_action=ToolAction(
                    tool="shell", arguments={"command": 'python -c "pass"'}
                ),
            ),
            AgentDecision(action="complete", completion_message="done"),
        ]),
    )

    wait_until(lambda: store.get_task(task.id).status == TaskStatus.WAITING_APPROVAL)
    approval = store.list_pending_approvals(task.id)[0]
    manager.decide_approval(approval.id, approved=True, scope="once", actor="api")
    wait_until(lambda: store.get_task(task.id).status == TaskStatus.SUCCEEDED)
    manager.shutdown()


def test_cancel_wakes_waiting_worker_and_persists_cancelled(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    manager = TaskManager(store)
    task = Task(workspace=str(tmp_path), goal="shell")
    manager.submit(
        task,
        LoopSpec(goal="shell"),
        MockLLMProvider([
            AgentDecision(
                action="tool_call",
                tool_action=ToolAction(
                    tool="shell", arguments={"command": 'python -c "pass"'}
                ),
            ),
        ]),
    )

    wait_until(lambda: store.get_task(task.id).status == TaskStatus.WAITING_APPROVAL)
    manager.cancel(task.id)
    wait_until(lambda: store.get_task(task.id).status == TaskStatus.CANCELLED)
    manager.shutdown()


@pytest.mark.parametrize(
    ("failure", "safe_report"),
    [
        (ProviderRequestError("sentinel-secret-provider"), "Provider 请求失败。"),
        (RuntimeError("sentinel-secret-unexpected"), "任务执行失败。"),
    ],
)
def test_background_failures_use_fixed_reports_without_persisting_exception_details(
    tmp_path, failure: Exception, safe_report: str
) -> None:
    class FailingProvider:
        def decide(self, context: str) -> AgentDecision:
            raise failure

    store = SQLiteStore(tmp_path / "state.db")
    manager = TaskManager(store)
    task = Task(workspace=str(tmp_path), goal="fail", mode=PermissionMode.PLAN)

    manager.submit(task, LoopSpec(goal="fail"), FailingProvider())
    wait_until(lambda: store.get_task(task.id).status == TaskStatus.FAILED)

    event = store.events_after(task.id, 0)[-1]
    assert event.payload["report"] == safe_report
    assert "sentinel-secret" not in event.model_dump_json()
    assert b"sentinel-secret" not in (tmp_path / "state.db").read_bytes()
    manager.shutdown()


def test_manager_startup_isolates_interrupted_tasks(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(
        Task(workspace=str(tmp_path), goal="recover", status=TaskStatus.RUNNING),
        LoopSpec(goal="recover"),
    )

    manager = TaskManager(store)

    assert store.get_task(task.id).status == TaskStatus.NEEDS_REVIEW
    assert store.get_recovery(task.id) == TaskRecovery(
        required=True, reason="服务重启后需人工复核"
    )
    assert [event.type for event in store.events_after(task.id, 0)] == ["recovery_required"]
    manager.shutdown()


def test_recover_restarts_from_persisted_spec_and_clears_recovery(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(
        Task(workspace=str(tmp_path), goal="stale", status=TaskStatus.NEEDS_REVIEW),
        LoopSpec(goal="persisted-goal"),
    )
    store.save_recovery(task.id, TaskRecovery(required=True, reason="服务重启后需人工复核"))
    manager = TaskManager(store)
    provider = MockLLMProvider([AgentDecision(action="complete", completion_message="done")])

    running = manager.recover(task.id, provider)
    wait_until(lambda: store.get_task(task.id).status == TaskStatus.SUCCEEDED)

    assert running.status == TaskStatus.RUNNING
    assert store.get_recovery(task.id) == TaskRecovery(
        required=False, reason="服务重启后需人工复核"
    )
    events = store.events_after(task.id, 0)
    assert events[0].type == "recovery_started"
    assert events[0].payload == {"reason": "用户确认从头重新执行"}
    assert events[-1].type == "task_completed"
    assert provider.contexts_seen
    assert "persisted-goal" in provider.contexts_seen[0]
    assert "stale" not in provider.contexts_seen[0]
    manager.shutdown()


@pytest.mark.parametrize(
    ("task_status", "recovery", "loop_spec", "message"),
    [
        (TaskStatus.NEEDS_REVIEW, None, LoopSpec(goal="recover"), "not restart-recoverable"),
        (
            TaskStatus.NEEDS_REVIEW,
            TaskRecovery(required=False, reason="服务重启后需人工复核"),
            LoopSpec(goal="recover"),
            "not restart-recoverable",
        ),
        (
            TaskStatus.RUNNING,
            TaskRecovery(required=True, reason="服务重启后需人工复核"),
            LoopSpec(goal="recover"),
            "not awaiting recovery",
        ),
        (
            TaskStatus.NEEDS_REVIEW,
            TaskRecovery(required=True, reason="服务重启后需人工复核"),
            None,
            "not restart-recoverable",
        ),
    ],
)
def test_recover_rejects_non_recoverable_tasks_without_creating_runtime(
    tmp_path,
    task_status: TaskStatus,
    recovery: TaskRecovery | None,
    loop_spec: LoopSpec | None,
    message: str,
) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    manager = TaskManager(store)
    task = Task(workspace=str(tmp_path), goal="recover", status=task_status)
    if loop_spec is not None:
        store.create_task(task, loop_spec)
    else:
        store.create_task(task, LoopSpec(goal="recover"))
        store.connection.execute("DELETE FROM specs WHERE task_id = ?", (task.id,))
        store.connection.commit()
    if recovery is not None:
        store.save_recovery(task.id, recovery)

    with pytest.raises(ValueError, match=message):
        manager.recover(
            task.id,
            MockLLMProvider([AgentDecision(action="complete", completion_message="done")]),
        )

    assert task.id not in manager._runtimes
    if recovery is not None:
        assert store.get_recovery(task.id) == recovery
    assert all(event.type != "recovery_started" for event in store.events_after(task.id, 0))
    manager.shutdown()


def test_deciding_orphaned_approval_conflicts_without_creating_runtime(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(
        Task(workspace=str(tmp_path), goal="recover", status=TaskStatus.NEEDS_REVIEW),
        LoopSpec(goal="recover"),
    )
    approval = store.save_approval(
        Approval(task_id=task.id, tool_call_id="tool-1", reason="shell requires approval")
    )
    manager = TaskManager(store)

    with pytest.raises(ValueError, match="approval runtime conflict"):
        manager.decide_approval(approval.id, approved=True, scope="once", actor="api")

    assert task.id not in manager._runtimes
    assert store.get_approval(approval.id).status == "pending"
    manager.shutdown()


def test_concurrent_recover_claims_task_only_once_across_connections(tmp_path) -> None:
    class SlowSpecStore(SQLiteStore):
        def __init__(self, path) -> None:
            super().__init__(path)

        def get_spec(self, task_id: str) -> LoopSpec | None:
            time.sleep(0.05)
            return super().get_spec(task_id)

    class BlockingProvider:
        def __init__(self, release: Event) -> None:
            self._release = release
            self._lock = Lock()
            self.calls = 0

        def decide(self, context: str) -> AgentDecision:
            del context
            with self._lock:
                self.calls += 1
            self._release.wait(timeout=2)
            return AgentDecision(action="complete", completion_message="done")

    path = tmp_path / "state.db"
    seed = SQLiteStore(path)
    task = seed.create_task(
        Task(workspace=str(tmp_path), goal="recover", status=TaskStatus.NEEDS_REVIEW),
        LoopSpec(goal="recover"),
    )
    seed.save_recovery(task.id, TaskRecovery(required=True, reason="服务重启后需人工复核"))

    start = Barrier(2)
    manager_a = TaskManager(SlowSpecStore(path))
    manager_b = TaskManager(SlowSpecStore(path))
    release = Event()
    provider = BlockingProvider(release)
    outcomes: list[object] = []

    def recover(manager: TaskManager) -> None:
        try:
            start.wait(timeout=2)
            outcomes.append(manager.recover(task.id, provider))
        except Exception as exc:  # pragma: no cover - assertions inspect concrete values
            outcomes.append(exc)

    thread_a = Thread(target=recover, args=(manager_a,))
    thread_b = Thread(target=recover, args=(manager_b,))
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    release.set()
    wait_until(lambda: provider.calls == 1)
    wait_until(lambda: seed.get_task(task.id).status == TaskStatus.SUCCEEDED)

    successes = [outcome for outcome in outcomes if isinstance(outcome, Task)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], ValueError)
    assert str(failures[0]) in {"not awaiting recovery", "not restart-recoverable"}
    assert provider.calls == 1
    assert [event.type for event in seed.events_after(task.id, 0)].count("recovery_started") == 1
    assert [event.type for event in seed.events_after(task.id, 0)].count("task_completed") == 1

    manager_a.shutdown()
    manager_b.shutdown()
