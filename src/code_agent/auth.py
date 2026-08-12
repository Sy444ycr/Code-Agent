from __future__ import annotations

import os
import re

import keyring

SERVICE_NAME = "code-agent"
_PROVIDER_NAME_PATTERN = re.compile(r"[a-z0-9_-]+")
_PROVIDER_DEVELOPMENT_SECRET_NAMES: set[str] = set()


def normalize_provider_name(provider: str) -> str:
    normalized = provider.lower()
    if not _PROVIDER_NAME_PATTERN.fullmatch(normalized):
        raise ValueError("provider name must contain only lowercase letters, digits, '-' and '_'")
    return normalized


def _provider_development_secret_name(provider: str) -> str:
    encoded = provider.upper().replace("_", "_U").replace("-", "_H")
    return f"CODE_AGENT_PROVIDER_{encoded}_API_KEY"


def provider_secret_environment_names() -> set[str]:
    return set(_PROVIDER_DEVELOPMENT_SECRET_NAMES)


def set_secret(provider: str, value: str) -> None:
    keyring.set_password(SERVICE_NAME, normalize_provider_name(provider), value)


def has_secret(provider: str) -> bool:
    return keyring.get_password(SERVICE_NAME, normalize_provider_name(provider)) is not None


def clear_secret(provider: str) -> None:
    try:
        keyring.delete_password(SERVICE_NAME, normalize_provider_name(provider))
    except keyring.errors.PasswordDeleteError:
        pass


def get_secret(provider: str) -> str | None:
    return keyring.get_password(SERVICE_NAME, normalize_provider_name(provider))


def get_provider_secret(provider: str, *, allow_development_fallback: bool) -> str | None:
    normalized = normalize_provider_name(provider)
    secret = keyring.get_password(SERVICE_NAME, normalized)
    if secret is not None or not allow_development_fallback:
        return secret
    environment_name = _provider_development_secret_name(normalized)
    _PROVIDER_DEVELOPMENT_SECRET_NAMES.add(environment_name)
    return os.environ.get(environment_name)
