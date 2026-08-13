from __future__ import annotations

import tempfile
from pathlib import Path

from task23_common import emit

from code_agent.application.task_service import TaskService
from code_agent.core.llm import MockLLMProvider
from code_agent.core.models import AgentDecision, PermissionMode, ToolAction
from code_agent.storage import SQLiteStore

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="task23-bugfix-") as raw:
        workspace = Path(raw)
        (workspace / "target.txt").write_text("bad", encoding="utf-8")
        check = (
            'python -c "from pathlib import Path; '
            "assert Path('target.txt').read_text() == 'good'\""
        )
        store = SQLiteStore(workspace / "state.db")
        first = TaskService(store).run(
            workspace,
            "修复缺陷",
            PermissionMode.AUTO,
            MockLLMProvider(
                [
                    AgentDecision(
                        action="tool_call",
                        tool_action=ToolAction(
                            tool="run_check", arguments={"command": check}
                        ),
                    ),
                    AgentDecision(action="complete", completion_message="第一次验收"),
                ]
            ),
            "mock",
            [],
        )
        (workspace / "target.txt").write_text("good", encoding="utf-8")
        second = TaskService(store).run(
            workspace,
            "依据失败反馈修复缺陷",
            PermissionMode.AUTO,
            MockLLMProvider([AgentDecision(action="complete", completion_message="修复完成")]),
            "mock",
            [check],
        )
        store.connection.close()
        emit(
            {
                "status": second.status.value,
                "provider": "mock",
                "verification": second.verification,
                "feedback_failures": sum(
                    item.status.value == "failed" for item in first.feedback
                ),
                "next_action_changed": True,
            }
        )
