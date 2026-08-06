from code_agent.core.context import ContextBuilder
from code_agent.core.feedback import FeedbackAdapter
from code_agent.core.hooks import HookRunner
from code_agent.core.llm import MockLLMProvider
from code_agent.core.loop import LoopController
from code_agent.core.memory import InMemoryMemoryStore
from code_agent.core.models import ActionType, AgentDecision, LoopSpec, Task, TaskStatus, ToolAction
from code_agent.core.policy import PolicyEngine
from code_agent.core.tools import ToolExecutor


def test_mock_loop_continues_after_failed_check_and_then_succeeds(tmp_path) -> None:
    (tmp_path / "test_demo.py").write_text("def test_demo():\n    assert True\n", encoding="utf-8")
    task = Task(workspace=str(tmp_path), goal="run checks")
    spec = LoopSpec(
        goal="run checks", acceptance_checks=["python -m pytest -q"], iteration_budget=3
    )
    provider = MockLLMProvider(
        [
            AgentDecision(
                action=ActionType.TOOL_CALL,
                tool_action=ToolAction(
                    tool="run_check", arguments={"command": 'python -c \\"raise SystemExit(1)\\"'}
                ),
            ),
            AgentDecision(
                action=ActionType.TOOL_CALL,
                tool_action=ToolAction(
                    tool="run_check", arguments={"command": "python -m pytest -q"}
                ),
            ),
            AgentDecision(action=ActionType.COMPLETE, completion_message="checks passed"),
        ]
    )
    controller = LoopController(
        provider=provider,
        policy=PolicyEngine(),
        tools=ToolExecutor(),
        feedback=FeedbackAdapter(),
        context=ContextBuilder(InMemoryMemoryStore()),
        hooks=HookRunner(),
    )
    result = controller.run(task, spec)
    assert result.status == TaskStatus.SUCCEEDED
    assert len(provider.contexts_seen) >= 2
    assert any(signal.status.value == "failed" for signal in result.feedback)
