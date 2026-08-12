import getpass
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from code_agent import cli
from code_agent.cli import app
from code_agent.core.llm import OpenAICompatibleProvider


def test_cli_help_lists_run_and_auth() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
    assert "auth" in result.output


def test_invalid_mock_scenario_does_not_expose_input_values(tmp_path: Path) -> None:
    scenario = tmp_path / "decisions.json"
    scenario.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "action": "complete",
                        "api_key": "secret-value",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["run", str(tmp_path), "goal", "--mock-decisions", str(scenario)],
    )

    assert result.exit_code == 2
    assert "secret-value" not in result.output
    assert "Mock 场景无效。" in result.output


def test_build_provider_resolves_profile_and_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / ".code-agent"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[providers.openai]\nbase_url = "https://example.com/v1/"\nmodel = "gpt-test"\n',
        encoding="utf-8",
    )
    captured: list[tuple[str, bool]] = []

    def get_provider_secret(provider: str, *, allow_development_fallback: bool) -> str:
        captured.append((provider, allow_development_fallback))
        return "secret-value"

    monkeypatch.setattr("code_agent.cli.auth.get_provider_secret", get_provider_secret)

    provider, provider_name = cli.build_provider("OpenAI", tmp_path)

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider_name == "openai"
    assert provider.base_url == "https://example.com/v1"
    assert provider.model == "gpt-test"
    assert provider.api_key_getter() == "secret-value"
    assert captured == [("openai", False)]


def test_build_provider_rejects_missing_secret_before_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / ".code-agent"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[providers.openai]\nbase_url = "https://example.com/v1"\nmodel = "gpt-test"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("code_agent.cli.auth.get_provider_secret", lambda *args, **kwargs: None)

    with pytest.raises(ValueError, match="Provider 密钥未配置"):
        cli.build_provider("openai", tmp_path)


def test_auth_status_normalizes_name_without_printing_secret(monkeypatch) -> None:
    captured: list[str] = []

    def has_secret(provider: str) -> bool:
        captured.append(provider)
        return True

    monkeypatch.setattr("code_agent.auth.has_secret", has_secret)
    result = CliRunner().invoke(app, ["auth", "status", "OpenAI"])

    assert result.exit_code == 0
    assert captured == ["openai"]
    assert "openai" in result.output
    assert "configured" in result.output.lower()
    assert "sk-" not in result.output


@pytest.mark.parametrize("command", ["set", "clear"])
def test_auth_mutations_normalize_name(
    command: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[tuple[str, str | None]] = []
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "secret-value")
    monkeypatch.setattr(
        "code_agent.auth.set_secret",
        lambda provider, value: captured.append((provider, value)),
    )
    monkeypatch.setattr(
        "code_agent.auth.clear_secret", lambda provider: captured.append((provider, None))
    )

    result = CliRunner().invoke(app, ["auth", command, "OpenAI"])

    assert result.exit_code == 0
    assert captured == [("openai", "secret-value" if command == "set" else None)]
    assert "secret-value" not in result.output


def test_auth_backend_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_provider: str) -> bool:
        raise RuntimeError("keyring raw failure secret-value")

    monkeypatch.setattr("code_agent.auth.has_secret", fail)

    result = CliRunner().invoke(app, ["auth", "status", "openai"])

    assert result.exit_code == 2
    assert "无法访问 Provider 凭据" in result.output
    assert "keyring raw failure" not in result.output
    assert "secret-value" not in result.output
