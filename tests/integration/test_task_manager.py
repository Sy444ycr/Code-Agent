import time

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
