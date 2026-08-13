from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from code_agent.api.schemas import ApprovalDecisionRequest, TaskCreate
from code_agent.application.providers import ProviderFactoryError, build_provider
from code_agent.application.task_manager import TaskManager
from code_agent.core.models import LoopSpec, Task, TaskStatus
from code_agent.storage import SQLiteStore


def create_app(
    store: SQLiteStore | None = None,
    controller_factory: Any | None = None,
    state_path: Path | None = None,
) -> FastAPI:
    del controller_factory
    app = FastAPI(title="Code-Agent")
    app.state.store = store or SQLiteStore(state_path or Path(".code-agent/state.db"))
    app.state.manager = TaskManager(app.state.store)

    @app.on_event("shutdown")
    def shutdown() -> None:
        app.state.manager.shutdown()

    @app.post("/api/tasks", status_code=201)
    def create_task(request: TaskCreate) -> dict[str, object]:
        workspace = Path(request.workspace).resolve()
        if not workspace.is_dir():
            raise HTTPException(status_code=400, detail="workspace does not exist")
        try:
            provider, provider_name = build_provider(
                request.provider,
                workspace,
                mock_decisions=request.mock_decisions if request.provider == "mock" else None,
            )
        except ProviderFactoryError as exc:
            raise HTTPException(status_code=400, detail="Provider 配置不可用。") from exc
        task = Task(
            workspace=str(workspace),
            goal=request.goal,
            mode=request.mode,
            provider=provider_name,
        )
        spec = LoopSpec(goal=request.goal, acceptance_checks=request.acceptance_checks)
        running = app.state.manager.submit(task, spec, provider)
        return _task_response(running, [])

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, object]:
        task = app.state.store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        spec = app.state.store.get_spec(task_id)
        approvals = app.state.store.list_pending_approvals(task_id)
        response = _task_response(task, approvals)
        response["loop_spec"] = spec.model_dump(mode="json") if spec else None
        return response

    @app.get("/api/tasks/{task_id}/report")
    def get_report(task_id: str) -> dict[str, object]:
        task = _require_task(task_id, app.state.store)
        event = _completed_event(task_id, app.state.store)
        payload = event.payload if event else {}
        return {
            "id": task.id,
            "status": task.status.value,
            "report": payload.get("report", ""),
            "changed_files": payload.get("changed_files", []),
            "feedback": payload.get("feedback", []),
            "verification": payload.get("verification", []),
        }

    @app.get("/api/tasks/{task_id}/diff")
    def get_diff(task_id: str) -> dict[str, object]:
        task = _require_task(task_id, app.state.store)
        try:
            result = subprocess.run(
                ["git", "-C", task.workspace, "diff", "--"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {"id": task.id, "diff": ""}
        return {"id": task.id, "diff": result.stdout if result.returncode == 0 else ""}

    @app.post("/api/tasks/{task_id}/cancel")
    def cancel_task(task_id: str) -> dict[str, object]:
        try:
            task = app.state.manager.cancel(task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="task not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _task_response(task, app.state.store.list_pending_approvals(task_id))

    @app.post("/api/tasks/{task_id}/resume")
    def resume_task(task_id: str) -> dict[str, object]:
        try:
            task = app.state.manager.resume(task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="task not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _task_response(task, app.state.store.list_pending_approvals(task_id))

    @app.get("/api/tasks/{task_id}/events")
    def events(task_id: str, after: int = Query(default=0, ge=0)) -> dict[str, object]:
        _require_task(task_id, app.state.store)
        return {
            "events": [
                event.model_dump(mode="json")
                for event in app.state.store.events_after(task_id, after)
            ]
        }

    @app.get("/api/tasks/{task_id}/events/stream")
    def event_stream(task_id: str, after: int = Query(default=0, ge=0)) -> StreamingResponse:
        _require_task(task_id, app.state.store)

        def generate() -> Iterator[str]:
            cursor = after
            while True:
                events = app.state.store.events_after(task_id, cursor)
                for event in events:
                    cursor = event.sequence
                    yield _format_sse(event)
                task = app.state.store.get_task(task_id)
                if task is not None and task.status in _TERMINAL_STATES and not events:
                    return
                app.state.manager.wait_for_event(task_id, cursor, timeout=0.5)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/api/approvals/{approval_id}/decision")
    def decide_approval(
        approval_id: str, request: ApprovalDecisionRequest
    ) -> dict[str, object]:
        if request.scope not in {"once", "task"}:
            raise HTTPException(status_code=422, detail="scope must be once or task")
        try:
            approval = app.state.manager.decide_approval(
                approval_id,
                request.approved,
                request.scope,
                request.actor,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="approval not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"approval": approval.model_dump(mode="json")}

    return app


def _require_task(task_id: str, store: SQLiteStore) -> Task:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


def _completed_event(task_id: str, store: SQLiteStore) -> Any | None:
    events = store.events_after(task_id, 0)
    for event in reversed(events):
        if event.type == "task_completed":
            return event
    return None


def _task_response(task: Task, approvals: list[Any]) -> dict[str, object]:
    return {
        "id": task.id,
        "status": task.status.value,
        "workspace": task.workspace,
        "goal": task.goal,
        "mode": task.mode.value,
        "provider": task.provider,
        "pending_approvals": [approval.model_dump(mode="json") for approval in approvals],
    }


def _format_sse(event: Any) -> str:
    return f"id: {event.sequence}\nevent: {event.type}\ndata: {event.model_dump_json()}\n\n"


_TERMINAL_STATES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.NEEDS_REVIEW,
    TaskStatus.BLOCKED,
    TaskStatus.FAILED,
    TaskStatus.BUDGET_EXHAUSTED,
    TaskStatus.CANCELLED,
}
