from __future__ import annotations

import keyring

SERVICE_NAME = "code-agent"


def set_secret(provider: str, value: str) -> None:
    keyring.set_password(SERVICE_NAME, provider, value)


def has_secret(provider: str) -> bool:
    return keyring.get_password(SERVICE_NAME, provider) is not None


def clear_secret(provider: str) -> None:
    try:
        keyring.delete_password(SERVICE_NAME, provider)
    except keyring.errors.PasswordDeleteError:
        pass


def get_secret(provider: str) -> str | None:
    return keyring.get_password(SERVICE_NAME, provider)
