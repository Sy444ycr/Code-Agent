import json
import subprocess

from typer.testing import CliRunner

from code_agent.cli import app


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
