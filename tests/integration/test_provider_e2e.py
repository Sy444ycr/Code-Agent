import os
from pathlib import Path

import pytest

from code_agent.cli import build_provider
from code_agent.core.models import AgentDecision


@pytest.mark.skipif(
    os.environ.get("CODE_AGENT_RUN_PROVIDER_E2E") != "1",
    reason="真实 Provider E2E 需要显式启用",
)
def test_configured_provider_returns_a_structured_decision(tmp_path: Path) -> None:
    provider, _ = build_provider(
        os.environ.get("CODE_AGENT_PROVIDER_E2E_NAME", "openai"), tmp_path
    )

    decision = provider.decide("只返回 action 为 complete 的 JSON 决策")

    assert isinstance(decision, AgentDecision)
