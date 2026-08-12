from code_agent.application.task_service import TaskService
from code_agent.core.llm import MockLLMProvider
from code_agent.core.models import AgentDecision, PermissionMode, TaskStatus, ToolAction
from code_agent.storage import SQLiteStore


def test_task_service_uses_injected_provider_and_persists_name(tmp_path) -> None:
    provider = MockLLMProvider([AgentDecision(action="complete")])
    service = TaskService(SQLiteStore(tmp_path / "state.db"))

    result = service.run(tmp_path, "finish", PermissionMode.AUTO, provider, "openai", [])

    assert result.status == TaskStatus.SUCCEEDED
    assert service.store.get_task(result.events[0].task_id).provider == "openai"
    assert provider.contexts_seen


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
        provider=MockLLMProvider([
            AgentDecision(
                action="tool_call",
                tool_action=ToolAction(
                    tool="write_file", arguments={"path": "target.txt", "content": "after"}
                ),
            ),
            AgentDecision(action="complete", completion_message="done"),
        ]),
        provider_name="mock",
        acceptance_checks=[acceptance_check],
    )

    task_id = result.events[0].task_id
    assert result.status == TaskStatus.SUCCEEDED
    assert (tmp_path / "target.txt").read_text(encoding="utf-8") == "after"
    assert store.get_task(task_id).status == TaskStatus.SUCCEEDED
    assert store.events_after(task_id, 0)[-1].type == "task_completed"
