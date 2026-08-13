from threading import Thread

from code_agent.core.models import (
    ActionType,
    AgentDecision,
    Approval,
    LoopSpec,
    Task,
    TaskRecovery,
    TaskStatus,
)
from code_agent.storage import SQLiteStore


def test_events_are_ordered_and_replayable(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(Task(workspace="/repo", goal="goal"), LoopSpec(goal="goal"))
    first = store.append_event(task.id, "task_started", {})
    second = store.append_event(task.id, "decision_made", {"action": "stop"})
    assert first.sequence == 1
    assert second.sequence == 2
    assert [event.sequence for event in store.events_after(task.id, first.sequence)] == [2]


def test_checkpoint_roundtrip(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(Task(workspace="/repo", goal="goal"), LoopSpec(goal="goal"))
    store.save_checkpoint(task.id, {"iteration": 2, "pending_action": "approval_1"})
    assert store.load_checkpoint(task.id) == {"iteration": 2, "pending_action": "approval_1"}


def test_recovery_roundtrip(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(Task(workspace="/repo", goal="goal"), LoopSpec(goal="goal"))
    recovery = TaskRecovery(
        required=True,
        reason="服务重启后需人工复核",
        mock_decisions=[AgentDecision(action=ActionType.STOP, rationale="manual review needed")],
    )

    store.save_recovery(task.id, recovery)

    assert store.get_recovery(task.id) == recovery


def test_store_creates_parent_directory_for_state_database(tmp_path) -> None:
    path = tmp_path / ".code-agent" / "state.db"

    SQLiteStore(path)

    assert path.exists()


def test_task_status_and_approval_roundtrip(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(Task(workspace="/repo", goal="goal"), LoopSpec(goal="goal"))
    completed = task.model_copy(update={"status": TaskStatus.SUCCEEDED})
    approval = Approval(tool_call_id="tool-1", reason="shell requires approval")

    store.update_task(completed)
    store.save_approval(approval)

    assert store.get_task(task.id) == completed
    assert store.get_approval(approval.id) == approval


def test_approval_roundtrip_keeps_task_id_and_decision(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(Task(workspace="/repo", goal="goal"), LoopSpec(goal="goal"))
    approval = store.save_approval(
        Approval(task_id=task.id, tool_call_id="tool-1", reason="shell requires approval")
    )

    decided = store.decide_approval(approval.id, approved=True, scope="task", actor="api")

    assert decided.task_id == task.id
    assert decided.status == "approved"
    assert store.list_pending_approvals(task.id) == []


def test_concurrent_event_writes_keep_unique_order(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    task = store.create_task(Task(workspace="/repo", goal="goal"), LoopSpec(goal="goal"))
    errors: list[Exception] = []

    def append() -> None:
        try:
            store.append_event(task.id, "feedback", {})
        except Exception as exc:
            errors.append(exc)

    threads = [Thread(target=append) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert [event.sequence for event in store.events_after(task.id, 0)] == list(range(1, 9))


def test_isolate_interrupted_tasks_marks_only_non_terminal_tasks_once(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "state.db")
    loop_spec = LoopSpec(goal="goal")
    pending = store.create_task(Task(workspace="/repo", goal="goal"), loop_spec)
    running = store.create_task(
        Task(workspace="/repo", goal="goal", status=TaskStatus.RUNNING), loop_spec
    )
    waiting = store.create_task(
        Task(workspace="/repo", goal="goal", status=TaskStatus.WAITING_APPROVAL), loop_spec
    )
    finished = store.create_task(
        Task(workspace="/repo", goal="goal", status=TaskStatus.SUCCEEDED), loop_spec
    )

    first_pass = store.isolate_interrupted_tasks()
    second_pass = store.isolate_interrupted_tasks()

    assert {task.id for task in first_pass} == {pending.id, running.id, waiting.id}
    assert second_pass == []
    assert store.get_task(pending.id).status == TaskStatus.NEEDS_REVIEW
    assert store.get_task(running.id).status == TaskStatus.NEEDS_REVIEW
    assert store.get_task(waiting.id).status == TaskStatus.NEEDS_REVIEW
    assert store.get_task(finished.id).status == TaskStatus.SUCCEEDED
    assert store.get_recovery(pending.id).reason == "服务重启后需人工复核"
    assert store.get_recovery(running.id).reason == "服务重启后需人工复核"
    assert store.get_recovery(waiting.id).reason == "服务重启后需人工复核"
    assert [event.type for event in store.events_after(pending.id, 0)] == ["recovery_required"]
    assert [event.type for event in store.events_after(running.id, 0)] == ["recovery_required"]
    assert [event.type for event in store.events_after(waiting.id, 0)] == ["recovery_required"]
    assert store.events_after(finished.id, 0) == []
