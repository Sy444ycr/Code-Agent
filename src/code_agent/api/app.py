from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from code_agent.api.schemas import TaskCreate
from code_agent.core.models import LoopSpec, Task
from code_agent.storage import SQLiteStore


def create_app(
    store: SQLiteStore | None = None,
    controller_factory: Callable[..., Any] | None = None,
    state_path: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Code-Agent")
    app.state.store = store or SQLiteStore(state_path or Path(".code-agent/state.db"))

    @app.post("/api/tasks", status_code=201)
    def create_task(request: TaskCreate) -> dict[str, object]:
        workspace = Path(request.workspace)
        if not workspace.exists():
            raise HTTPException(status_code=400, detail="workspace does not exist")
        task = Task(
            workspace=str(workspace),
            goal=request.goal,
            mode=request.mode,
            provider=request.provider,
        )
        app.state.store.create_task(
            task, LoopSpec(goal=request.goal, acceptance_checks=request.acceptance_checks)
        )
        app.state.store.append_event(task.id, "task_started", {})
        return {
            "id": task.id,
            "status": task.status.value,
            "workspace": task.workspace,
            "goal": task.goal,
            "mode": task.mode.value,
            "provider": task.provider,
        }

    @app.get("/api/tasks/{task_id}/events")
    def events(task_id: str, after: int = Query(default=0)) -> dict[str, object]:
        return {
            "events": [
                event.model_dump(mode="json")
                for event in app.state.store.events_after(task_id, after)
            ]
        }

    @app.get("/api/tasks/{task_id}/events/stream")
    def event_stream(task_id: str, after: int = Query(default=0)) -> StreamingResponse:
        events = app.state.store.events_after(task_id, after)
        body = "".join(
            f"id: {event.sequence}\nevent: {event.type}\ndata: {event.model_dump_json()}\n\n"
            for event in events
        )
        return StreamingResponse(iter([body]), media_type="text/event-stream")

    return app
