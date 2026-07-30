"""Environment-backed configuration without secret-value logging."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from doc_inspector.errors import ConfigurationError
from doc_inspector.types import ProviderName


class ProviderConfig(BaseModel):
    """Validated settings for one model provider."""

    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    model: str
    api_key: SecretStr = Field(repr=False)


class AppSettings(BaseSettings):
    """Settings loaded from process environment and an optional dotenv file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    google_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        repr=False,
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
        repr=False,
    )
    gemini_model: str | None = Field(default=None, validation_alias="GEMINI_MODEL")
    openai_model: str | None = Field(default=None, validation_alias="OPENAI_MODEL")
    model_max_tokens: int = Field(default=4096, ge=256, le=65536)
    gradio_server_name: Literal["127.0.0.1", "0.0.0.0"] = Field(
        default="127.0.0.1",
        validation_alias="GRADIO_SERVER_NAME",
    )
    gradio_server_port: int = Field(
        default=7861,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("GRADIO_SERVER_PORT", "PORT"),
    )
    public_max_requests_per_hour: int = Field(
        default=0,
        ge=0,
        le=10000,
        validation_alias="PUBLIC_MAX_REQUESTS_PER_HOUR",
    )
    colqwen_model: str = Field(
        default="vidore/colqwen2-v1.0-hf",
        validation_alias="COLQWEN_MODEL",
    )
    evidence_ocr_enabled: bool = Field(
        default=False,
        validation_alias="EVIDENCE_OCR",
    )
    evidence_ocr_languages: str = Field(
        default="chi_tra+chi_sim+eng",
        validation_alias="EVIDENCE_OCR_LANGUAGES",
    )

    max_file_bytes: int = 25 * 1024 * 1024
    max_pdf_pages: int = 10
    render_dpi: int = 200
    max_image_long_edge: int = 2400

    def provider_config(self, provider: ProviderName) -> ProviderConfig:
        """Return provider settings or raise an actionable, secret-safe error."""

        if provider == "gemini":
            api_key = self.google_api_key
            model = self.gemini_model
            missing = []
            if api_key is None or not api_key.get_secret_value().strip():
                missing.append("GOOGLE_API_KEY（或相容的 GEMINI_API_KEY）")
            if model is None or not model.strip():
                missing.append("GEMINI_MODEL")
        elif provider == "openai":
            api_key = self.openai_api_key
            model = self.openai_model
            missing = []
            if api_key is None or not api_key.get_secret_value().strip():
                missing.append("OPENAI_API_KEY")
            if model is None or not model.strip():
                missing.append("OPENAI_MODEL")
        else:
            raise ConfigurationError(f"不支援的供應商：{provider!r}。")

        if missing:
            joined = "、".join(missing)
            raise ConfigurationError(f"缺少 {joined}；請在 .env 設定後再試。")

        assert api_key is not None
        assert model is not None
        return ProviderConfig(provider=provider, model=model.strip(), api_key=api_key)


def load_settings(env_file: Path | None = Path(".env")) -> AppSettings:
    """Load settings; passing ``None`` disables dotenv-file loading."""

    return AppSettings(_env_file=env_file)
