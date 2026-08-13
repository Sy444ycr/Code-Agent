from pathlib import Path

from typer.testing import CliRunner

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
