from __future__ import annotations

import argparse
from pathlib import Path

from fastapi import FastAPI, HTTPException
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
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        requested = (dist / path).resolve()
        if not requested.is_relative_to(dist.resolve()) or not requested.is_file():
            requested = dist / "index.html"
        return FileResponse(requested)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check packaged WebUI assets")
    parser.add_argument("--check", action="store_true", help="verify WebUI assets are available")
    arguments = parser.parse_args()
    if not arguments.check:
        parser.print_help()
        return 0
    if static_dist_path() is None:
        print("Web assets unavailable")
        return 1
    print("Web assets available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
