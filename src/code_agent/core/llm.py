from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import httpx

from code_agent.core.models import AgentDecision


class ProviderExhaustedError(RuntimeError):
    pass


class LLMProvider(Protocol):
    def decide(self, context: str) -> AgentDecision: ...


class MockLLMProvider:
    def __init__(self, decisions: list[AgentDecision]) -> None:
        self.decisions = list(decisions)
        self.contexts_seen: list[str] = []

    def decide(self, context: str) -> AgentDecision:
        self.contexts_seen.append(context)
        if not self.decisions:
            raise ProviderExhaustedError("mock decision sequence exhausted")
        return self.decisions.pop(0)


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, model: str, api_key_getter: Callable[[], str]) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_getter = api_key_getter

    def decide(self, context: str) -> AgentDecision:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": context}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"schema": AgentDecision.model_json_schema()},
            },
        }
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key_getter()}"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return AgentDecision.model_validate_json(content)
