import subprocess
import sys


def test_mock_feedback_demo_runs() -> None:
    result = subprocess.run(
        [sys.executable, "demos/mock_feedback_loop.py"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "guardrail=denied" in result.stdout
    assert "feedback_loop=succeeded" in result.stdout
