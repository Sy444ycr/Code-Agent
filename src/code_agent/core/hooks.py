from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from code_agent.core.models import FeedbackSignal, FeedbackStatus


class HookPoint(StrEnum):
    ON_TASK_START = "on_task_start"
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    ON_ITERATION_END = "on_iteration_end"
    BEFORE_TASK_COMPLETE = "before_task_complete"
    ON_TASK_END = "on_task_end"


class HookResult:
    def __init__(
        self, blocked: bool = False, feedback: list[FeedbackSignal] | None = None, message: str = ""
    ) -> None:
        self.blocked = blocked
        self.__dict__["feedback"] = feedback or []
        self.message = message

    @classmethod
    def feedback(cls, source: str, status: FeedbackStatus, summary: str) -> HookResult:
        return cls(feedback=[FeedbackSignal(source=source, status=status, summary=summary)])


class HookRunner:
    def __init__(self) -> None:
        self._hooks: dict[HookPoint, list[Callable[[dict[str, Any]], HookResult]]] = {}

    def register(self, point: HookPoint, hook: Callable[[dict[str, Any]], HookResult]) -> None:
        self._hooks.setdefault(point, []).append(hook)

    def run(self, point: HookPoint, payload: dict[str, Any]) -> HookResult:
        result = HookResult()
        for hook in self._hooks.get(point, []):
            try:
                current = hook(payload)
            except Exception as exc:
                current = HookResult.feedback(f"hook:{point}", FeedbackStatus.FAILED, str(exc))
            result.blocked = result.blocked or current.blocked
            result.__dict__["feedback"].extend(current.__dict__["feedback"])
            if current.message:
                result.message = current.message
        return result
