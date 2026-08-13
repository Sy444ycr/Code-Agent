import json
import subprocess
import sys
from pathlib import Path

import pytest

DEMO_DIR = Path(__file__).parents[2] / "demos"


@pytest.mark.parametrize(
    "name",
    ["task23_feature.py", "task23_bugfix.py", "task23_tests.py", "task23_refactor.py"],
)
def test_task23_demo_reports_safe_success(name: str) -> None:
    result = subprocess.run(
        [sys.executable, str(DEMO_DIR / name)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["provider"] == "mock"
    assert payload["verification"]
    assert "secret" not in result.stdout.lower()
    assert "transcript" not in result.stdout.lower()


def test_bugfix_demo_proves_feedback_changed_next_action() -> None:
    result = subprocess.run(
        [sys.executable, str(DEMO_DIR / "task23_bugfix.py")],
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    assert payload["feedback_failures"] >= 1
    assert payload["next_action_changed"] is True
