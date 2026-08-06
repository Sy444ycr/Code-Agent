from __future__ import annotations

from pathlib import Path
from threading import Lock


class WorkspaceBoundaryError(ValueError):
    """Raised when a path escapes the workspace root."""


class Workspace:
    def __init__(
        self, root: Path, max_file_bytes: int = 1_000_000, max_output_chars: int = 20_000
    ) -> None:
        self.root = root.resolve()
        self.max_file_bytes = max_file_bytes
        self.max_output_chars = max_output_chars
        self._write_lock = Lock()
        self._write_task_id: str | None = None

    def resolve_inside(self, path: str) -> Path:
        target = (self.root / path).resolve()
        if target != self.root and self.root not in target.parents:
            raise WorkspaceBoundaryError(f"path escapes workspace: {path}")
        return target

    def acquire_write_lock(self, task_id: str) -> bool:
        if not self._write_lock.acquire(blocking=False):
            return False
        self._write_task_id = task_id
        return True

    def release_write_lock(self, task_id: str) -> None:
        if self._write_task_id == task_id:
            self._write_task_id = None
            self._write_lock.release()
