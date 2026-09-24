"""Typed application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, cast

from fastapi import Request
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API process.

    Secrets are intentionally absent from this foundation. Future provider keys
    are supplied only through environment variables or a secret manager.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="The Lens of Truth API", validation_alias="APP_NAME")
    app_env: Literal["development", "test", "staging", "production"] = Field(
        default="development", validation_alias="APP_ENV"
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    api_v1_prefix: str = Field(default="/v1", validation_alias="API_V1_PREFIX")
    database_url: str = Field(
        default="postgresql+psycopg://lens:lens@localhost:5432/lens",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    cors_origins_raw: str = Field(default="http://localhost:5173", validation_alias="CORS_ORIGINS")

    upload_storage_path: Path = Field(
        default=Path("./runtime/uploads"), validation_alias="UPLOAD_STORAGE_PATH"
    )
    upload_max_bytes: int = Field(
        default=10 * 1024 * 1024, ge=1, validation_alias="UPLOAD_MAX_BYTES"
    )
    upload_max_pixels: int = Field(default=25_000_000, ge=1, validation_alias="UPLOAD_MAX_PIXELS")
    upload_retention_hours: int = Field(
        default=24, ge=1, le=24, validation_alias="UPLOAD_RETENTION_HOURS"
    )
    retention_cleanup_interval_seconds: int = Field(
        default=300, ge=60, validation_alias="RETENTION_CLEANUP_INTERVAL_SECONDS"
    )
    ocr_timeout_seconds: float = Field(default=20.0, gt=0, validation_alias="OCR_TIMEOUT_SECONDS")
    ocr_executable: str = Field(default="tesseract", validation_alias="OCR_EXECUTABLE")
    claim_extractor_provider: Literal["disabled", "openai_compatible"] = Field(
        default="disabled", validation_alias="CLAIM_EXTRACTOR_PROVIDER"
    )
    claim_extractor_base_url: str | None = Field(
        default=None, validation_alias="CLAIM_EXTRACTOR_BASE_URL"
    )
    claim_extractor_model: str | None = Field(
        default=None, validation_alias="CLAIM_EXTRACTOR_MODEL"
    )
    claim_extractor_api_key: SecretStr | None = Field(
        default=None, validation_alias="CLAIM_EXTRACTOR_API_KEY"
    )
    claim_extractor_timeout_seconds: float = Field(
        default=20.0, gt=0, validation_alias="CLAIM_EXTRACTOR_TIMEOUT_SECONDS"
    )
    claim_extractor_max_claims: int = Field(
        default=20, ge=1, le=50, validation_alias="CLAIM_EXTRACTOR_MAX_CLAIMS"
    )

    @property
    def cors_origins(self) -> list[str]:
        """Return normalized origins from the comma-separated environment value."""

        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Create one immutable settings instance per process."""

    return Settings()


def get_runtime_settings(request: Request) -> Settings:
    """Use the application-factory settings instead of re-reading environment state."""

    return cast(Settings, request.app.state.settings)
