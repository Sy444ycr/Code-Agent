import json

import httpx
import pytest

from code_agent.core.llm import (
    MockLLMProvider,
    OpenAICompatibleProvider,
    ProviderExhaustedError,
    ProviderRequestError,
)
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


def test_openai_compatible_provider_posts_schema_and_parses_decision() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"action":"complete"}'}}]},
        )

    provider = OpenAICompatibleProvider(
        "https://provider.example/v1",
        "model-x",
        lambda: "secret-value",
        httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert provider.decide("context").action == ActionType.COMPLETE
    assert seen["url"] == "https://provider.example/v1/chat/completions"
    assert seen["authorization"] == "Bearer secret-value"
    assert seen["payload"] == {
        "model": "model-x",
        "messages": [{"role": "user", "content": "context"}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"schema": AgentDecision.model_json_schema()},
        },
    }


def test_provider_error_does_not_echo_secret_or_response_body() -> None:
    provider = OpenAICompatibleProvider(
        "https://provider.example/v1",
        "model-x",
        lambda: "secret-value",
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, text="upstream-internal")
            )
        ),
    )

    with pytest.raises(ProviderRequestError) as exc_info:
        provider.decide("context")

    assert "secret-value" not in str(exc_info.value)
    assert "upstream-internal" not in str(exc_info.value)
