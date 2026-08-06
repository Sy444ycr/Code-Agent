from __future__ import annotations

import re

from code_agent.core.memory import InMemoryMemoryStore
from code_agent.core.models import FeedbackSignal, LoopSpec, Task


class ContextBuilder:
    def __init__(self, memory: InMemoryMemoryStore, max_chars: int = 4_000) -> None:
        self.memory = memory
        self.max_chars = max_chars

    def build(self, task: Task, loop_spec: LoopSpec, feedback: list[FeedbackSignal]) -> str:
        def redact(value: str) -> str:
            return re.sub(
                r"sk-[A-Za-z0-9_-]{8,}|(?i:api[_-]?key|token|secret)=\S+", "[REDACTED]", value
            )

        memories = self.memory.search(task.workspace, [], limit=10)
        sections = [
            f"Goal\n{task.goal}",
            f"Acceptance Checks\n{chr(10).join(loop_spec.acceptance_checks)}",
            f"Permission Mode\n{task.mode.value}",
            "Recent Feedback\n" + "\n".join(redact(item.summary) for item in feedback),
            "Relevant Memory\n" + "\n".join(redact(item.content) for item in memories),
            "Unfinished Work\n",
        ]
        result = "\n\n".join(sections)
        return result[: self.max_chars]
