from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field


class Event(BaseModel):
    id: str
    task_id: str
    sequence: int
    type: str
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventSink(Protocol):
    def emit(self, task_id: str, event_type: str, payload: dict[str, Any]) -> Event:
        """Persist and publish an ordered event."""
