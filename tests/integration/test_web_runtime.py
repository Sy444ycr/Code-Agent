from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from code_agent.api.app import create_app
from code_agent.cli import app
from code_agent.web_assets import static_dist_path


def test_web_command_passes_host_and_port_to_uvicorn(monkeypatch) -> None:
    calls: list[tuple[str, str, int]] = []
    monkeypatch.setattr(
        "uvicorn.run",
        lambda target, host, port: calls.append((target, host, port)),
    )

    result = CliRunner().invoke(app, ["web", "--host", "127.0.0.1", "--port", "8123"])

    assert result.exit_code == 0
    assert calls == [("code_agent.api.app:create_app", "127.0.0.1", 8123)]


def test_static_dist_path_returns_path_or_none() -> None:
    result = static_dist_path()

    assert result is None or isinstance(result, Path)


def test_package_assets_take_precedence_and_api_routes_are_not_spa_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_dist = tmp_path / "package" / "web_dist"
    source_dist = tmp_path / "source" / "web" / "dist"
    package_dist.mkdir(parents=True)
    source_dist.mkdir(parents=True)
    (package_dist / "index.html").write_text("package", encoding="utf-8")
    (source_dist / "index.html").write_text("source", encoding="utf-8")
    monkeypatch.setattr(
        "code_agent.web_assets._asset_candidates", lambda: [package_dist, source_dist]
    )

    assert static_dist_path() == package_dist
    client = TestClient(create_app(state_path=tmp_path / "state.db"))
    assert client.get("/").text == "package"
    assert client.get("/client/route").text == "package"
    assert client.get("/api/tasks/not-found").status_code == 404
