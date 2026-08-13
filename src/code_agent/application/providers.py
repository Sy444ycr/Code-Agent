from __future__ import annotations

from pathlib import Path

from code_agent import auth
from code_agent.config import resolve_provider_profile
from code_agent.core.llm import LLMProvider, MockLLMProvider, OpenAICompatibleProvider
from code_agent.core.models import AgentDecision


class ProviderFactoryError(ValueError):
    """用户可见的 Provider 装配错误。"""


def build_provider(
    name: str,
    workspace: Path,
    *,
    mock_decisions: list[AgentDecision] | None = None,
    allow_development_fallback: bool = False,
) -> tuple[LLMProvider, str]:
    try:
        provider_name = auth.normalize_provider_name(name)
    except ValueError as exc:
        raise ProviderFactoryError("Provider 名称无效。") from exc
    if provider_name == "mock":
        if mock_decisions is None:
            raise ProviderFactoryError("Mock Provider 必须显式提供决策。")
        return MockLLMProvider(mock_decisions), provider_name
    try:
        profile = resolve_provider_profile(provider_name, workspace)
        api_key = auth.get_provider_secret(
            provider_name,
            allow_development_fallback=allow_development_fallback,
        )
        if api_key is None:
            raise ProviderFactoryError("Provider 凭据不可用。")
        return OpenAICompatibleProvider(
            base_url=profile.base_url,
            model=profile.model,
            api_key_getter=lambda: api_key,
        ), provider_name
    except ProviderFactoryError:
        raise
    except Exception as exc:
        raise ProviderFactoryError("Provider 配置不可用。") from exc
