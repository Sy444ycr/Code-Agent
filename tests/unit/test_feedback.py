from code_agent.core.feedback import FeedbackAdapter
from code_agent.core.models import FeedbackStatus, ToolResult


def test_successful_command_becomes_passed_feedback() -> None:
    signal = FeedbackAdapter().from_tool_result(
        ToolResult(tool="run_check", exit_code=0, stdout="ok")
    )
    assert signal.status == FeedbackStatus.PASSED
    assert signal.fingerprint is None


def test_pytest_failure_extracts_test_name() -> None:
    output = "FAILED tests/test_math.py::test_addition - AssertionError: assert 1 == 2"
    signal = FeedbackAdapter().from_tool_result(
        ToolResult(tool="run_check", exit_code=1, stdout=output)
    )
    assert signal.status == FeedbackStatus.FAILED
    assert signal.fingerprint == "pytest:tests/test_math.py::test_addition"
    assert "test_addition" in signal.summary


def test_generic_failure_uses_exit_code_and_stderr_hash() -> None:
    signal = FeedbackAdapter().from_tool_result(
        ToolResult(tool="shell", exit_code=2, stderr="compiler exploded")
    )
    assert signal.status == FeedbackStatus.FAILED
    assert signal.fingerprint.startswith("shell:2:")
