import pytest

from code_agent.core.llm import MockLLMProvider, ProviderExhaustedError
from code_agent.core.models import ActionType, AgentDecision, ToolAction


def test_mock_provider_returns_decisions_in_order() -> None:
    provider = MockLLMProvider(
        [
            AgentDecision(
                action=ActionType.TOOL_CALL,
                tool_action=ToolAction(tool="read_file", arguments={"path": "README.md"}),
            ),
            AgentDecision(action=ActionType.STOP, rationale="done"),
        ]
    )
    assert provider.decide("ctx").action == ActionType.TOOL_CALL
    assert provider.decide("ctx").action == ActionType.STOP


def test_mock_provider_exhaustion_is_deterministic() -> None:
    with pytest.raises(ProviderExhaustedError):
        MockLLMProvider([]).decide("ctx")
