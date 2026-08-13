from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

from code_agent.core.events import Event
from code_agent.core.models import Approval, LoopSpec, Task, TaskRecovery, TaskStatus


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.executescript(
            "CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, data TEXT);"
            "CREATE TABLE IF NOT EXISTS specs(task_id TEXT PRIMARY KEY, data TEXT);"
            "CREATE TABLE IF NOT EXISTS events(id TEXT, task_id TEXT, sequence INTEGER, "
            "type TEXT, payload TEXT, created_at TEXT, PRIMARY KEY(task_id, sequence));"
            "CREATE TABLE IF NOT EXISTS checkpoints(task_id TEXT PRIMARY KEY, payload TEXT);"
            "CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, data TEXT);"
            "CREATE TABLE IF NOT EXISTS recoveries(task_id TEXT PRIMARY KEY, data TEXT);"
        )

    def _write_task(self, task: Task) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO tasks VALUES (?, ?)", (task.id, task.model_dump_json())
        )

    def _write_spec(self, task_id: str, loop_spec: LoopSpec) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO specs VALUES (?, ?)",
            (task_id, loop_spec.model_dump_json()),
        )

    def _write_approval(self, approval: Approval) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO approvals VALUES (?, ?)",
            (approval.id, approval.model_dump_json()),
        )

    def _write_recovery(self, task_id: str, recovery: TaskRecovery) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO recoveries VALUES (?, ?)",
            (task_id, recovery.model_dump_json()),
        )

    def _append_event(self, task_id: str, event_type: str, payload: dict[str, object]) -> Event:
        sequence = self.connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE task_id = ?", (task_id,)
        ).fetchone()[0]
        event = Event(
            id=str(uuid4()), task_id=task_id, sequence=sequence, type=event_type, payload=payload
        )
        self.connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.id,
                task_id,
                sequence,
                event_type,
                json.dumps(payload),
                event.created_at.isoformat(),
            ),
        )
        return event

    def create_task(
        self,
        task: Task,
        loop_spec: LoopSpec,
        recovery: TaskRecovery | None = None,
    ) -> Task:
        with self._lock:
            self._write_task(task)
            self._write_spec(task.id, loop_spec)
            if recovery is not None:
                self._write_recovery(task.id, recovery)
            self.connection.commit()
        return task

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT data FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return Task.model_validate_json(row[0]) if row else None

    def update_task(self, task: Task) -> Task:
        with self._lock:
            self._write_task(task)
            self.connection.commit()
        return task

    def save_approval(self, approval: Approval) -> Approval:
        with self._lock:
            self._write_approval(approval)
            self.connection.commit()
        return approval

    def get_approval(self, approval_id: str) -> Approval | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT data FROM approvals WHERE id = ?", (approval_id,)
            ).fetchone()
        return Approval.model_validate_json(row[0]) if row else None

    def save_recovery(self, task_id: str, recovery: TaskRecovery) -> TaskRecovery:
        with self._lock:
            self._write_recovery(task_id, recovery)
            self.connection.commit()
        return recovery

    def get_recovery(self, task_id: str) -> TaskRecovery | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT data FROM recoveries WHERE task_id = ?", (task_id,)
            ).fetchone()
        return TaskRecovery.model_validate_json(row[0]) if row else None

    def get_spec(self, task_id: str) -> LoopSpec | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT data FROM specs WHERE task_id = ?", (task_id,)
            ).fetchone()
        return LoopSpec.model_validate_json(row[0]) if row else None

    def list_pending_approvals(self, task_id: str) -> list[Approval]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT data FROM approvals ORDER BY rowid"
            ).fetchall()
        return [
            approval
            for (data,) in rows
            if (approval := Approval.model_validate_json(data)).task_id == task_id
            and approval.status == "pending"
        ]

    def decide_approval(
        self,
        approval_id: str,
        approved: bool,
        scope: str,
        actor: str,
    ) -> Approval:
        with self._lock:
            row = self.connection.execute(
                "SELECT data FROM approvals WHERE id = ?", (approval_id,)
            ).fetchone()
            if row is None:
                raise KeyError(approval_id)
            current = Approval.model_validate_json(row[0])
            if current.status != "pending":
                raise ValueError(f"approval {approval_id} is already decided")
            decided = current.model_copy(
                update={
                    "status": "approved" if approved else "rejected",
                    "scope": scope,
                    "actor": actor,
                }
            )
            self._write_approval(decided)
            self.connection.commit()
        return decided

    def append_event(self, task_id: str, event_type: str, payload: dict[str, object]) -> Event:
        with self._lock:
            event = self._append_event(task_id, event_type, payload)
            self.connection.commit()
        return event

    def claim_recovery(self, task_id: str, reason: str) -> tuple[Task, LoopSpec]:
        with self._lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                task = self.get_task(task_id)
                recovery = self.get_recovery(task_id)
                loop_spec = self.get_spec(task_id)
                if (
                    task is None
                    or recovery is None
                    or not recovery.required
                    or loop_spec is None
                ):
                    raise ValueError("not restart-recoverable")
                if task.status != TaskStatus.NEEDS_REVIEW:
                    raise ValueError("not awaiting recovery")
                running = task.model_copy(
                    update={"status": TaskStatus.RUNNING, "goal": loop_spec.goal}
                )
                self._write_task(running)
                self._write_recovery(
                    task_id,
                    recovery.model_copy(update={"required": False}),
                )
                self._append_event(task_id, "recovery_started", {"reason": reason})
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise
        return running, loop_spec

    def isolate_interrupted_tasks(self) -> list[Task]:
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            rows = self.connection.execute("SELECT data FROM tasks ORDER BY rowid").fetchall()
            isolated: list[Task] = []
            recovery_reason = "服务重启后需人工复核"
            for (data,) in rows:
                task = Task.model_validate_json(data)
                if task.status not in {
                    TaskStatus.PENDING,
                    TaskStatus.RUNNING,
                    TaskStatus.WAITING_APPROVAL,
                }:
                    continue
                updated = task.model_copy(update={"status": TaskStatus.NEEDS_REVIEW})
                existing_recovery = self.get_recovery(task.id)
                recovery = (
                    existing_recovery.model_copy(
                        update={"required": True, "reason": recovery_reason}
                    )
                    if existing_recovery is not None
                    else TaskRecovery(required=True, reason=recovery_reason)
                )
                self._write_task(updated)
                self._write_recovery(task.id, recovery)
                self._append_event(task.id, "recovery_required", {"reason": recovery.reason})
                isolated.append(updated)
            self.connection.commit()
        return isolated

    def events_after(self, task_id: str, sequence: int) -> list[Event]:
        with self._lock:
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
        with self._lock:
            self.connection.execute(
                "INSERT OR REPLACE INTO checkpoints VALUES (?, ?)",
                (task_id, json.dumps(checkpoint)),
            )
            self.connection.commit()

    def load_checkpoint(self, task_id: str) -> dict[str, object] | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT payload FROM checkpoints WHERE task_id = ?", (task_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None
