import json

from typer.testing import CliRunner

from code_agent.cli import app


def test_status_command_prints_stable_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "code_agent.cli.TaskApiClient.get_status",
        lambda _client, task_id: {"id": task_id, "status": "succeeded"},
    )

    result = CliRunner().invoke(
        app, ["status", "task-1", "--url", "http://127.0.0.1:8000", "--json"]
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {"id": "task-1", "status": "succeeded"}


def test_attach_rejects_non_http_urls() -> None:
    result = CliRunner().invoke(app, ["attach", "file:///tmp/service"])

    assert result.exit_code == 2
    assert "服务地址无效" in result.output
