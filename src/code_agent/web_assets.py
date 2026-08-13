from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse


def static_dist_path() -> Path | None:
    candidates = [
        Path(__file__).resolve().parent / "web_dist",
        Path(__file__).resolve().parent.parent.parent / "web" / "dist",
    ]
    return next((candidate for candidate in candidates if candidate.is_dir()), None)


def mount_web_assets(app: FastAPI) -> None:
    dist = static_dist_path()
    if dist is None:
        return

    @app.get("/{path:path}")
    def serve_web(path: str) -> FileResponse:
        requested = (dist / path).resolve()
        if not str(requested).startswith(str(dist.resolve())) or not requested.is_file():
            requested = dist / "index.html"
        return FileResponse(requested)
