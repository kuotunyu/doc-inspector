from __future__ import annotations

import pytest

from doc_inspector.config import AppSettings
from doc_inspector.errors import ConfigurationError


PROVIDER_ENV_NAMES = (
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_MODEL",
    "OPENAI_MODEL",
    "PUBLIC_MAX_REQUESTS_PER_HOUR",
)


def clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROVIDER_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_google_api_key_is_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "canonical-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "fallback-secret")
    monkeypatch.setenv("GEMINI_MODEL", "configured-model")

    config = AppSettings(_env_file=None).provider_config("gemini")

    assert config.api_key.get_secret_value() == "canonical-secret"
    assert config.model == "configured-model"
    assert "canonical-secret" not in repr(config)


def test_gemini_key_fallback_is_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "fallback-secret")
    monkeypatch.setenv("GEMINI_MODEL", "configured-model")

    config = AppSettings(_env_file=None).provider_config("gemini")

    assert config.api_key.get_secret_value() == "fallback-secret"


def test_missing_provider_settings_are_actionable_and_secret_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)

    with pytest.raises(ConfigurationError) as exc_info:
        AppSettings(_env_file=None).provider_config("openai")

    message = str(exc_info.value)
    assert "OPENAI_API_KEY" in message
    assert "OPENAI_MODEL" in message
    assert ".env" in message


def test_model_string_is_loaded_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setenv("OPENAI_MODEL", "environment-model")

    config = AppSettings(_env_file=None).provider_config("openai")

    assert config.model == "environment-model"


def test_public_request_limit_defaults_off_and_loads_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_provider_env(monkeypatch)
    settings = AppSettings(_env_file=None)
    assert settings.public_max_requests_per_hour == 0

    monkeypatch.setenv("PUBLIC_MAX_REQUESTS_PER_HOUR", "60")
    settings = AppSettings(_env_file=None)
    assert settings.public_max_requests_per_hour == 60
