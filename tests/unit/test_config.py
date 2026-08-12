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


def test_profile_names_are_normalized_before_cross_layer_override(tmp_path: Path) -> None:
    user = tmp_path / "user.toml"
    user.write_text(
        '[providers.OpenAI]\nbase_url = "https://user.example/v1"\nmodel = "user"\n'
    )
    project = tmp_path / ".code-agent"
    project.mkdir()
    (project / "config.toml").write_text(
        '[providers.openai]\nbase_url = "https://project.example/v1"\nmodel = "project"\n'
    )

    profiles = load_provider_profiles(tmp_path, user)

    assert list(profiles) == ["openai"]
    assert profiles["openai"] == ProviderProfile(
        name="openai", base_url="https://project.example/v1", model="project"
    )
    assert resolve_provider_profile("OpenAI", tmp_path, user).model == "project"


def test_rejects_duplicate_profile_names_after_normalization(tmp_path: Path) -> None:
    config = tmp_path / ".code-agent"
    config.mkdir()
    (config / "config.toml").write_text(
        '[providers.OpenAI]\nbase_url = "https://one.example/v1"\nmodel = "one"\n'
        '[providers.openai]\nbase_url = "https://two.example/v1"\nmodel = "two"\n'
    )

    with pytest.raises(ProviderConfigurationError, match="Provider"):
        load_provider_profiles(tmp_path)


def test_rejects_invalid_profile_table_name_with_safe_error(tmp_path: Path) -> None:
    config = tmp_path / ".code-agent"
    config.mkdir()
    (config / "config.toml").write_text(
        '[providers."openai/secret"]\nbase_url = "https://example.com/v1"\nmodel = "x"\n'
    )

    with pytest.raises(ProviderConfigurationError, match="Provider") as exc_info:
        load_provider_profiles(tmp_path)

    assert "openai/secret" not in str(exc_info.value)


def test_rejects_non_local_http_profile_before_provider_creation(tmp_path: Path) -> None:
    config = tmp_path / ".code-agent"
    config.mkdir()
    (config / "config.toml").write_text(
        '[providers.remote]\nbase_url = "http://example.com/v1"\nmodel = "x"\n'
    )

    with pytest.raises(ProviderConfigurationError, match="HTTPS"):
        resolve_provider_profile("remote", tmp_path)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api-key@example.com/v1",
        "https://example.com/v1?api_key=secret",
        "https://example.com/v1#secret",
        "https://example.com:not-a-port/v1",
    ],
)
def test_rejects_provider_urls_with_secret_bearing_or_invalid_components(
    tmp_path: Path, base_url: str
) -> None:
    config = tmp_path / ".code-agent"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[providers.remote]\nbase_url = "{base_url}"\nmodel = "x"\n'
    )

    with pytest.raises(ProviderConfigurationError, match="Provider URL") as exc_info:
        resolve_provider_profile("remote", tmp_path)

    assert "secret" not in str(exc_info.value)


def test_rejects_name_field_in_profile(tmp_path: Path) -> None:
    config = tmp_path / ".code-agent"
    config.mkdir()
    (config / "config.toml").write_text(
        '[providers.remote]\nname = "override"\n'
        'base_url = "https://example.com/v1"\nmodel = "x"\n'
    )

    with pytest.raises(ProviderConfigurationError, match="未知字段"):
        load_provider_profiles(tmp_path)
