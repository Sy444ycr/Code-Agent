from code_agent.core.models import LoopSpec, Task
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
