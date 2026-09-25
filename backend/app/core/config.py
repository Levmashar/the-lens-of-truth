"""Typed application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, cast

from fastapi import Request
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API process.

    Provider credentials are supplied only through environment variables or a
    secret manager, never source code.
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
    claim_extractor_provider: Literal["disabled", "openai_compatible", "miri"] = Field(
        default="miri", validation_alias="CLAIM_EXTRACTOR_PROVIDER"
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
        default=55.0, gt=0, le=60, validation_alias="CLAIM_EXTRACTOR_TIMEOUT_SECONDS"
    )
    claim_extractor_total_timeout_seconds: float = Field(
        default=115.0, gt=0, le=120,
        validation_alias="CLAIM_EXTRACTOR_TOTAL_TIMEOUT_SECONDS",
    )
    claim_extractor_max_claims: int = Field(
        default=20, ge=1, le=50, validation_alias="CLAIM_EXTRACTOR_MAX_CLAIMS"
    )
    mesh_index_path: Path = Field(
        default=Path("./runtime/mesh/mesh.sqlite3"), validation_alias="MESH_INDEX_PATH"
    )
    ncbi_tool: str = Field(default="the_lens_of_truth", validation_alias="NCBI_TOOL")
    ncbi_email: str | None = Field(default=None, validation_alias="NCBI_EMAIL")
    ncbi_api_key: SecretStr | None = Field(default=None, validation_alias="NCBI_API_KEY")
    pubmed_timeout_seconds: float = Field(
        default=12.0, gt=0, le=30, validation_alias="PUBMED_TIMEOUT_SECONDS"
    )
    pubmed_max_retries: int = Field(default=1, ge=0, le=2,
                                    validation_alias="PUBMED_MAX_RETRIES")
    pubmed_query_retmax: int = Field(default=10, ge=1, le=12,
                                     validation_alias="PUBMED_QUERY_RETMAX")
    pubmed_cache_ttl_seconds: int = Field(
        default=21600, ge=60, le=86400, validation_alias="PUBMED_CACHE_TTL_SECONDS"
    )
    pubmed_selected_evidence_limit: int = Field(
        default=8, ge=1, le=20, validation_alias="PUBMED_SELECTED_EVIDENCE_LIMIT"
    )
    pubmed_max_passages_per_document: int = Field(
        default=1, ge=1, le=3, validation_alias="PUBMED_MAX_PASSAGES_PER_DOCUMENT"
    )
    crossref_mailto: str | None = Field(default=None, validation_alias="CROSSREF_MAILTO")
    crossref_timeout_seconds: float = Field(
        default=8.0, gt=0, le=20, validation_alias="CROSSREF_TIMEOUT_SECONDS"
    )
    crossref_max_retries: int = Field(
        default=1, ge=0, le=2, validation_alias="CROSSREF_MAX_RETRIES"
    )
    crossref_cache_ttl_seconds: int = Field(
        default=3600, ge=60, le=86400, validation_alias="CROSSREF_CACHE_TTL_SECONDS"
    )
    crossref_total_timeout_seconds: float = Field(
        default=30.0, gt=0, le=60, validation_alias="CROSSREF_TOTAL_TIMEOUT_SECONDS"
    )

    @field_validator("ncbi_tool")
    @classmethod
    def valid_ncbi_tool(cls, value: str) -> str:
        if not value or any(character.isspace() for character in value):
            raise ValueError("NCBI_TOOL must be non-empty and contain no spaces")
        return value

    @field_validator("ncbi_email", "crossref_mailto")
    @classmethod
    def valid_ncbi_email(cls, value: str | None) -> str | None:
        if value is not None and (
            "@" not in value or any(character.isspace() for character in value)
        ):
            raise ValueError("Contact email must be an email address")
        return value

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
