"""Configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    api_key: str = ""
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


class BrowserExtensionsConfig(BaseModel):
    nopecha_path: str = "extensions/nopecha"
    discord_token_path: str = "extensions/discord-token-login"
    load_nopecha: bool = True  # load NopeCHA unpacked ext when extensions are enabled


class BrowserConfig(BaseModel):
    headless: bool = True
    max_concurrent: int = 3
    job_timeout_seconds: int = 300
    navigation_timeout_ms: int = 60000
    action_timeout_ms: int = 30000
    viewport_width: int = 1280
    viewport_height: int = 720
    args: list[str] = Field(default_factory=list)
    extensions: BrowserExtensionsConfig = Field(default_factory=BrowserExtensionsConfig)
    user_data_base: str = "data/browser_profiles"
    executable_path: str = ""  # auto-detect brave/chrome
    shared_profile: bool = True  # reuse profile — keeps cf_clearance cookies
    shared_profile_id: str = "default"
    system_profile_path: str = ""  # optional: use real Brave profile dir (extensions baked in)
    load_extensions_at_startup: bool = True
    load_extensions_after_cloudflare: bool = False
    engine: str = "zendriver"  # zendriver | playwright


class JobsConfig(BaseModel):
    max_retries: int = 3
    retry_delay_seconds: int = 5
    cleanup_after_hours: int = 24
    store_path: str = "data/jobs.db"
    artifacts_dir: str = "data/artifacts"


class CaptchaConfig(BaseModel):
    solved_selector: str = 'input[name="cf-turnstile-response"]'
    solved_attribute: str = "value"
    max_wait_seconds: int = 120
    poll_interval_seconds: int = 2
    nopecha_api_key: str = ""
    mode: str = "auto"  # auto | api | extension


class ButtonConfig(BaseModel):
    text: str = ""
    selectors: list[str] = Field(default_factory=list)


class TokenLoginConfig(BaseModel):
    popup_path: str = "popup.html"
    token_input_selectors: list[str] = Field(default_factory=list)
    submit_selectors: list[str] = Field(default_factory=list)
    wait_after_login_seconds: int = 5


class DiscordConfig(BaseModel):
    oauth_url_pattern: str = "discord.com/oauth2"
    authorize_button: ButtonConfig = Field(default_factory=ButtonConfig)
    token_login: TokenLoginConfig = Field(default_factory=TokenLoginConfig)


class SuccessConfig(BaseModel):
    text_patterns: list[str] = Field(default_factory=list)
    max_wait_seconds: int = 60


class CloudflareConfig(BaseModel):
    max_wait_seconds: int = 240
    cf_clearance_required: bool = True


class PoketwoConfig(BaseModel):
    verify_url_pattern: str = "verify.poketwo.net/captcha/"
    captcha: CaptchaConfig = Field(default_factory=CaptchaConfig)
    cloudflare: CloudflareConfig = Field(default_factory=CloudflareConfig)
    verify_button: ButtonConfig = Field(default_factory=ButtonConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    success: SuccessConfig = Field(default_factory=SuccessConfig)


class AutomationConfig(BaseModel):
    poketwo: PoketwoConfig = Field(default_factory=PoketwoConfig)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"
    file: str = "data/logs/cap-solver.log"
    rotation: str = "50 MB"
    retention: str = "7 days"


class PlatformConfig(BaseModel):
    display: str = ":99"


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    jobs: JobsConfig = Field(default_factory=JobsConfig)
    automation: AutomationConfig = Field(default_factory=AutomationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    platform: PlatformConfig = Field(default_factory=PlatformConfig)

    @property
    def base_dir(self) -> Path:
        return Path(os.environ.get("CAPSOLVER_BASE_DIR", ".")).resolve()

    def resolve_path(self, relative: str) -> Path:
        return (self.base_dir / relative).resolve()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CAPSOLVER_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    api_key: str = ""
    config_path: str = "config/default.yaml"
    local_config_path: str = "config/local.yaml"


_settings: Settings | None = None
_config: AppConfig | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def load_config(
    config_path: str | None = None,
    local_config_path: str | None = None,
) -> AppConfig:
    global _config
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    settings = get_settings()
    base_path = Path(config_path or settings.config_path)
    local_path = Path(local_config_path or settings.local_config_path)

    data: dict[str, Any] = {}
    if base_path.exists():
        data = _load_yaml(base_path)
    if local_path.exists():
        data = _deep_merge(data, _load_yaml(local_path))

    config = AppConfig.model_validate(data)

    nopecha_key = os.getenv("NOPECHA_API_KEY", "").strip()
    if nopecha_key:
        config.automation.poketwo.captcha.nopecha_api_key = nopecha_key
    elif os.getenv("CAPSOLVER_AUTOMATION__POKETWO__CAPTCHA__NOPECHA_API_KEY"):
        config.automation.poketwo.captcha.nopecha_api_key = os.environ[
            "CAPSOLVER_AUTOMATION__POKETWO__CAPTCHA__NOPECHA_API_KEY"
        ]

    if settings.api_key:
        config.server.api_key = settings.api_key
    if os.environ.get("CAPSOLVER_SERVER__API_KEY"):
        config.server.api_key = os.environ["CAPSOLVER_SERVER__API_KEY"]

    _config = config
    return config


def get_config() -> AppConfig:
    global _config
    if _config is None:
        return load_config()
    return _config
