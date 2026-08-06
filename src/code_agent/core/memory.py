from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    workspace: str
    type: str
    tags: list[str] = Field(default_factory=list)
    content: str
    evidence: list[str] = Field(default_factory=list)
    verified_at: datetime | None = None


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self.entries: list[MemoryEntry] = []

    def add_candidate(self, entry: MemoryEntry) -> MemoryEntry:
        self.entries.append(entry)
        return entry

    def add_verified(self, entry: MemoryEntry) -> MemoryEntry:
        verified = entry.model_copy(update={"verified_at": datetime.now(UTC)})
        self.entries.append(verified)
        return verified

    def search(self, workspace: str, tags: list[str], limit: int) -> list[MemoryEntry]:
        return [
            entry
            for entry in self.entries
            if entry.workspace == workspace
            and entry.verified_at is not None
            and set(tags).issubset(entry.tags)
        ][:limit]
