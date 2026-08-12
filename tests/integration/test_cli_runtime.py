import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from code_agent.cli import app
from code_agent.core.llm import MockLLMProvider, ProviderRequestError
from code_agent.core.models import ActionType, AgentDecision


def test_cli_rejects_unknown_provider_without_loading_mock(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["run", str(tmp_path), "goal", "--provider", "missing"])

    assert result.exit_code == 2
    assert "Provider 档案不存在" in result.output
    assert "mock" not in result.output.lower()


def test_cli_runs_injected_openai_compatible_profile_without_mock_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "code_agent.cli.build_provider",
        lambda *args, **kwargs: (
            MockLLMProvider([AgentDecision(action=ActionType.COMPLETE)]),
            "openai",
        ),
    )

    result = CliRunner().invoke(
        app, ["run", str(tmp_path), "goal", "--provider", "openai", "--json"]
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["status"] == "succeeded"


def test_cli_rejects_mock_decisions_for_non_mock_provider(tmp_path: Path) -> None:
    scenario = tmp_path / "decisions.json"
    scenario.write_text('{"decisions": []}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(tmp_path),
            "goal",
            "--provider",
            "openai",
            "--mock-decisions",
            str(scenario),
        ],
    )

    assert result.exit_code == 2
    assert "非 Mock Provider 不接受 --mock-decisions" in result.output


def test_cli_reports_provider_request_error_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingProvider:
        def decide(self, context: str) -> AgentDecision:
            raise ProviderRequestError("Provider 请求失败。")

    monkeypatch.setattr(
        "code_agent.cli.build_provider", lambda *args, **kwargs: (FailingProvider(), "openai")
    )

    result = CliRunner().invoke(
        app, ["run", str(tmp_path), "goal", "--provider", "openai"]
    )

    assert result.exit_code == 2
    assert "Provider 请求失败" in result.output
    assert "Traceback" not in result.output


def test_cli_run_executes_mock_scenario_and_persists_evidence(tmp_path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "target.txt").write_text("before", encoding="utf-8")
    scenario = tmp_path / "decisions.json"
    scenario.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "action": "tool_call",
                        "tool_action": {
                            "tool": "write_file",
                            "arguments": {"path": "target.txt", "content": "after"},
                        },
                    },
                    {"action": "complete", "completion_message": "done"},
                ]
            }
        ),
        encoding="utf-8",
    )

    acceptance_check = (
        'python -c "from pathlib import Path; '
        "assert Path('target.txt').read_text() == 'after'\""
    )
    result = CliRunner().invoke(
        app,
        [
            "run",
            str(tmp_path),
            "update target",
            "--mock-decisions",
            str(scenario),
            "--check",
            acceptance_check,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["id"]
    assert payload["status"] == "succeeded"
    assert payload["changed_files"] == ["target.txt"]
    assert (tmp_path / ".code-agent" / "state.db").exists()


def test_cli_run_records_rejected_supervised_shell(tmp_path) -> None:
    scenario = tmp_path / "decisions.json"
    scenario.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "action": "tool_call",
                        "tool_action": {
                            "tool": "shell",
                            "arguments": {"command": 'python -c "pass"'},
                        },
                    },
                    {"action": "complete", "completion_message": "done"},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["run", str(tmp_path), "run shell", "--mock-decisions", str(scenario), "--json"],
        input="n\n",
    )

    assert result.exit_code == 1
    assert json.loads(result.output.splitlines()[-1])["status"] == "needs_review"
