from pathlib import Path

import pytest

from code_agent.config import (
    ProviderConfigurationError,
    ProviderProfile,
    load_provider_profiles,
    resolve_provider_profile,
)


def test_project_profile_replaces_same_named_user_profile(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text('[providers.openai]\nbase_url = "https://user.example/v1"\nmodel = "user"\n')
    project = tmp_path / ".code-agent"
    project.mkdir()
    (project / "config.toml").write_text(
        '[providers.openai]\nbase_url = "https://project.example/v1"\nmodel = "project"\n'
    )

    profiles = load_provider_profiles(tmp_path, user)

    assert profiles["openai"] == ProviderProfile(
        name="openai", base_url="https://project.example/v1", model="project"
    )


def test_rejects_non_local_http_profile_before_provider_creation(tmp_path: Path) -> None:
    config = tmp_path / ".code-agent"
    config.mkdir()
    (config / "config.toml").write_text(
        '[providers.remote]\nbase_url = "http://example.com/v1"\nmodel = "x"\n'
    )

    with pytest.raises(ProviderConfigurationError, match="HTTPS"):
        resolve_provider_profile("remote", tmp_path)


def test_rejects_name_field_in_profile(tmp_path: Path) -> None:
    config = tmp_path / ".code-agent"
    config.mkdir()
    (config / "config.toml").write_text(
        '[providers.remote]\nname = "override"\n'
        'base_url = "https://example.com/v1"\nmodel = "x"\n'
    )

    with pytest.raises(ProviderConfigurationError, match="未知字段"):
        load_provider_profiles(tmp_path)
