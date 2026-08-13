from pathlib import Path

import pytest

from code_agent.application.providers import ProviderFactoryError, build_provider
from code_agent.core.llm import MockLLMProvider
from code_agent.core.models import AgentDecision


def test_build_mock_provider_requires_explicit_decisions(tmp_path: Path) -> None:
    provider, name = build_provider(
        "mock",
        tmp_path,
        mock_decisions=[AgentDecision(action="complete", completion_message="done")],
    )

    assert isinstance(provider, MockLLMProvider)
    assert name == "mock"


def test_build_mock_provider_rejects_implicit_decisions(tmp_path: Path) -> None:
    with pytest.raises(ProviderFactoryError, match="Mock Provider"):
        build_provider("mock", tmp_path)
