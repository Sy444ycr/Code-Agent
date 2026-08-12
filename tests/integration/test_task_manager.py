import time

import pytest

from code_agent.application.task_manager import TaskManager
from code_agent.core.llm import MockLLMProvider, ProviderRequestError
from code_agent.core.models import (
    AgentDecision,
    LoopSpec,
    PermissionMode,
    Task,
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
