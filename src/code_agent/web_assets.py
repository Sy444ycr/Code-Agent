from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse


def _asset_candidates() -> list[Path]:
    return [
        Path(__file__).resolve().parent / "web_dist",
        Path(__file__).resolve().parents[2] / "web" / "dist",
    ]


def static_dist_path() -> Path | None:
    return next(
        (candidate for candidate in _asset_candidates() if (candidate / "index.html").is_file()),
        None,
    )


def mount_web_assets(app: FastAPI) -> None:
    dist = static_dist_path()
    if dist is None:
        return

    @app.get("/{path:path}")
    def serve_web(path: str) -> FileResponse:
        requested = (dist / path).resolve()
        if not requested.is_relative_to(dist.resolve()) or not requested.is_file():
            requested = dist / "index.html"
        return FileResponse(requested)
