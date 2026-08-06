from typer.testing import CliRunner

from code_agent.cli import app


def test_cli_help_lists_run_and_auth() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
    assert "auth" in result.output


def test_auth_status_does_not_print_secret(monkeypatch) -> None:
    monkeypatch.setattr("code_agent.auth.has_secret", lambda provider: True)
    result = CliRunner().invoke(app, ["auth", "status", "openai"])
    assert result.exit_code == 0
    assert "configured" in result.output.lower()
    assert "sk-" not in result.output
