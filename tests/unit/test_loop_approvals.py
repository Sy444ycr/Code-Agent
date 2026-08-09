from code_agent.core.feedback import FeedbackAdapter
from code_agent.core.llm import MockLLMProvider
from code_agent.core.loop import LoopController
from code_agent.core.models import (
    AgentDecision,
    ApprovalResolution,
    LoopSpec,
    PermissionMode,
    Task,
    TaskStatus,
    ToolAction,
)
from code_agent.core.policy import PolicyEngine
from code_agent.core.tools import ToolExecutor


def test_task_grant_allows_second_shell_without_second_prompt(tmp_path) -> None:
    answers: list[str] = []

    def approve(task: Task, action: ToolAction, decision: object) -> ApprovalResolution:
        answers.append(action.tool)
        return ApprovalResolution(approved=True, scope="task")

    loop = LoopController(
        provider=MockLLMProvider(
            [
                AgentDecision(
                    action="tool_call",
                    tool_action=ToolAction(
                        tool="shell", arguments={"command": 'python -c "pass"'}
                    ),
                ),
                AgentDecision(
                    action="tool_call",
                    tool_action=ToolAction(
                        tool="shell", arguments={"command": 'python -c "pass"'}
                    ),
                ),
                AgentDecision(action="complete", completion_message="done"),
            ]
        ),
        policy=PolicyEngine(),
        tools=ToolExecutor(),
        feedback=FeedbackAdapter(),
        approval_handler=approve,
    )

    result = loop.run(
        Task(workspace=str(tmp_path), goal="run", mode=PermissionMode.SUPERVISED),
        LoopSpec(goal="run"),
    )

    assert result.status == TaskStatus.SUCCEEDED
    assert answers == ["shell"]
    assert [event.type for event in result.events if event.type.startswith("approval_")] == [
        "approval_requested",
        "approval_decided",
    ]
