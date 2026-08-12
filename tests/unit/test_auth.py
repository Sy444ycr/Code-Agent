import pytest

from code_agent.auth import get_provider_secret, normalize_provider_name


def test_normalize_provider_name_rejects_characters_outside_allowed_set() -> None:
    with pytest.raises(ValueError, match="provider"):
        normalize_provider_name("OpenAI/production")


def test_get_provider_secret_uses_normalized_keyring_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, str]] = []

    def get_password(service: str, account: str) -> str:
        captured.append((service, account))
        return "keyring-secret"

    monkeypatch.setattr("code_agent.auth.keyring.get_password", get_password)

    assert get_provider_secret("OpenAI", allow_development_fallback=False) == "keyring-secret"
    assert captured == [("code-agent", "openai")]


def test_development_fallback_is_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("code_agent.auth.keyring.get_password", lambda *_: None)
    monkeypatch.setenv("CODE_AGENT_PROVIDER_OPENAI_API_KEY", "dev-secret")

    assert get_provider_secret("openai", allow_development_fallback=False) is None
    assert get_provider_secret("openai", allow_development_fallback=True) == "dev-secret"


def test_development_fallback_names_do_not_alias_hyphen_and_underscore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("code_agent.auth.keyring.get_password", lambda *_: None)
    monkeypatch.setenv("CODE_AGENT_PROVIDER_FOO_UBAR_API_KEY", "underscore-secret")
    monkeypatch.setenv("CODE_AGENT_PROVIDER_FOO_HBAR_API_KEY", "hyphen-secret")

    assert (
        get_provider_secret("foo_bar", allow_development_fallback=True)
        == "underscore-secret"
    )
    assert get_provider_secret("foo-bar", allow_development_fallback=True) == "hyphen-secret"
