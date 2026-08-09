from code_agent.application.task_service import TaskService
from code_agent.core.models import AgentDecision, PermissionMode, TaskStatus, ToolAction
from code_agent.storage import SQLiteStore


def test_task_service_runs_mock_decisions_and_persists_completion(tmp_path) -> None:
    store = SQLiteStore(tmp_path / ".code-agent" / "state.db")
    service = TaskService(store)

    acceptance_check = (
        'python -c "from pathlib import Path; '
        "assert Path('target.txt').read_text() == 'after'\""
    )
    result = service.run(
        workspace=tmp_path,
        goal="update target",
        mode=PermissionMode.SUPERVISED,
        decisions=[
            AgentDecision(
                action="tool_call",
                tool_action=ToolAction(
                    tool="write_file", arguments={"path": "target.txt", "content": "after"}
                ),
            ),
            AgentDecision(action="complete", completion_message="done"),
        ],
        acceptance_checks=[acceptance_check],
    )

    task_id = result.events[0].task_id
    assert result.status == TaskStatus.SUCCEEDED
    assert (tmp_path / "target.txt").read_text(encoding="utf-8") == "after"
    assert store.get_task(task_id).status == TaskStatus.SUCCEEDED
    assert store.events_after(task_id, 0)[-1].type == "task_completed"
