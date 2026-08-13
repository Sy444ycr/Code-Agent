from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from code_agent.application.task_service import TaskService
from code_agent.core.llm import MockLLMProvider
from code_agent.core.models import AgentDecision, PermissionMode
from code_agent.storage import SQLiteStore


def run_success(content: str, goal: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="task23-") as raw:
        workspace = Path(raw)
        target = workspace / "target.txt"
        target.write_text(content, encoding="utf-8")
        check = (
            'python -c "from pathlib import Path; '
            "assert Path('target.txt').read_text() == '"
            + content
            + "'\""
        )
        store = SQLiteStore(workspace / "state.db")
        result = TaskService(store).run(
            workspace,
            goal,
            PermissionMode.AUTO,
            MockLLMProvider(
                [
                    AgentDecision(
                        action="tool_call",
                        tool_action={
                            "tool": "write_file",
                            "arguments": {"path": "target.txt", "content": content},
                        },
                    ),
                    AgentDecision(action="complete", completion_message="验收通过"),
                ]
            ),
            "mock",
            [check],
        )
        payload = {
            "status": result.status.value,
            "provider": "mock",
            "verification": result.verification,
            "changed_files": result.changed_files,
        }
        store.connection.close()
        return payload


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
