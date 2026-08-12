from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, ValidationError


class AppConfig(BaseModel):
    api_base_url: str = "http://127.0.0.1:8000"
    state_path: str = ".code-agent/state.db"


class ProviderConfigurationError(ValueError):
    """可安全显示给用户的 Provider 配置错误。"""


class ProviderProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    base_url: str
    model: str


def default_user_config_path() -> Path:
    config_dir = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
    if config_dir is None:
        config_dir = str(Path.home() / ".config")
    return Path(config_dir) / "code-agent" / "config.toml"


def _read_profiles(path: Path) -> dict[str, ProviderProfile]:
    if not path.is_file():
        return {}

    try:
        content = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ProviderConfigurationError("Provider 配置文件无效。") from error

    if set(content) - {"providers"}:
        raise ProviderConfigurationError("Provider 配置包含未知字段。")
    providers = content.get("providers", {})
    if not isinstance(providers, Mapping):
        raise ProviderConfigurationError("Provider 配置无效。")

    profiles: dict[str, ProviderProfile] = {}
    for name, values in providers.items():
        if not isinstance(name, str) or not name.strip():
            raise ProviderConfigurationError("Provider 名称不能为空。")
        if not isinstance(values, Mapping):
            raise ProviderConfigurationError("Provider 配置无效。")
        if not isinstance(values.get("base_url"), str):
            raise ProviderConfigurationError("Provider URL 必须是字符串。")
        if not isinstance(values.get("model"), str) or not values["model"].strip():
            raise ProviderConfigurationError("Provider 模型不能为空。")
        try:
            profiles[name] = ProviderProfile(name=name, **values)
        except ValidationError as error:
            raise ProviderConfigurationError("Provider 配置包含未知字段。") from error
    return profiles


def load_provider_profiles(
    workspace: Path, user_config_path: Path | None = None
) -> dict[str, ProviderProfile]:
    user_profiles = _read_profiles(user_config_path or default_user_config_path())
    project_profiles = _read_profiles(workspace / ".code-agent" / "config.toml")
    return {**user_profiles, **project_profiles}


def resolve_provider_profile(
    name: str, workspace: Path, user_config_path: Path | None = None
) -> ProviderProfile:
    profiles = load_provider_profiles(workspace, user_config_path)
    try:
        profile = profiles[name]
    except KeyError as error:
        raise ProviderConfigurationError("未找到指定的 Provider 配置。") from error

    parsed = urlsplit(profile.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProviderConfigurationError("Provider URL 必须是有效的 HTTP(S) 地址。")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ProviderConfigurationError("非本地 Provider 必须使用 HTTPS。")
    return profile
