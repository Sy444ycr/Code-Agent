from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from code_agent.core.events import Event
from code_agent.core.models import LoopSpec, Task


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.executescript(
            "CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, data TEXT);"
            "CREATE TABLE IF NOT EXISTS specs(task_id TEXT PRIMARY KEY, data TEXT);"
            "CREATE TABLE IF NOT EXISTS events(id TEXT, task_id TEXT, sequence INTEGER, "
            "type TEXT, payload TEXT, created_at TEXT, PRIMARY KEY(task_id, sequence));"
            "CREATE TABLE IF NOT EXISTS checkpoints(task_id TEXT PRIMARY KEY, payload TEXT)"
        )

    def create_task(self, task: Task, loop_spec: LoopSpec) -> Task:
        self.connection.execute(
            "INSERT OR REPLACE INTO tasks VALUES (?, ?)", (task.id, task.model_dump_json())
        )
        self.connection.execute(
            "INSERT OR REPLACE INTO specs VALUES (?, ?)", (task.id, loop_spec.model_dump_json())
        )
        self.connection.commit()
        return task

    def append_event(self, task_id: str, type: str, payload: dict[str, object]) -> Event:
        sequence = self.connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE task_id = ?", (task_id,)
        ).fetchone()[0]
        event = Event(
            id=str(uuid4()), task_id=task_id, sequence=sequence, type=type, payload=payload
        )
        self.connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
            (event.id, task_id, sequence, type, json.dumps(payload), event.created_at.isoformat()),
        )
        self.connection.commit()
        return event

    def events_after(self, task_id: str, sequence: int) -> list[Event]:
        rows = self.connection.execute(
            "SELECT id, sequence, type, payload, created_at FROM events "
            "WHERE task_id = ? AND sequence > ? ORDER BY sequence",
            (task_id, sequence),
        ).fetchall()
        return [
            Event(
                id=row[0],
                task_id=task_id,
                sequence=row[1],
                type=row[2],
                payload=json.loads(row[3]),
                created_at=datetime.fromisoformat(row[4]),
            )
            for row in rows
        ]

    def save_checkpoint(self, task_id: str, checkpoint: dict[str, object]) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO checkpoints VALUES (?, ?)", (task_id, json.dumps(checkpoint))
        )
        self.connection.commit()

    def load_checkpoint(self, task_id: str) -> dict[str, object] | None:
        row = self.connection.execute(
            "SELECT payload FROM checkpoints WHERE task_id = ?", (task_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None
