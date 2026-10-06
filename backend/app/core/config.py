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
    debug_mode: bool = Field(default=False, validation_alias="DEBUG_MODE")
    authoritative_enabled: bool = Field(default=True, validation_alias="AUTHORITATIVE_ENABLED")
    authoritative_manifest_path: Path | None = Field(
        default=None, validation_alias="AUTHORITATIVE_MANIFEST_PATH",
    )
    authoritative_max_update_age_days: int = Field(
        default=3650, ge=1, le=36500, validation_alias="AUTHORITATIVE_MAX_UPDATE_AGE_DAYS",
    )
    authoritative_max_review_age_days: int = Field(
        default=90, ge=1, le=365, validation_alias="AUTHORITATIVE_MAX_REVIEW_AGE_DAYS",
    )
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
    judge_1_provider: Literal["miri", "openai_compatible", "paratera"] | None = Field(
        default=None, validation_alias="JUDGE_1_PROVIDER"
    )
    judge_1_model: str | None = Field(default=None, validation_alias="JUDGE_1_MODEL")
    judge_1_thinking_enabled: bool | None = Field(
        default=None, validation_alias="JUDGE_1_THINKING_ENABLED"
    )
    judge_1_model_family: str | None = Field(
        default=None, validation_alias="JUDGE_1_MODEL_FAMILY"
    )
    judge_1_base_url: str | None = Field(default=None, validation_alias="JUDGE_1_BASE_URL")
    judge_1_api_key: SecretStr | None = Field(default=None, validation_alias="JUDGE_1_API_KEY")
    judge_2_provider: Literal["miri", "openai_compatible", "paratera"] | None = Field(
        default=None, validation_alias="JUDGE_2_PROVIDER"
    )
    judge_2_model: str | None = Field(default=None, validation_alias="JUDGE_2_MODEL")
    judge_2_thinking_enabled: bool | None = Field(
        default=None, validation_alias="JUDGE_2_THINKING_ENABLED"
    )
    judge_2_model_family: str | None = Field(
        default=None, validation_alias="JUDGE_2_MODEL_FAMILY"
    )
    judge_2_base_url: str | None = Field(default=None, validation_alias="JUDGE_2_BASE_URL")
    judge_2_api_key: SecretStr | None = Field(default=None, validation_alias="JUDGE_2_API_KEY")
    judge_3_provider: Literal["miri", "openai_compatible", "paratera"] | None = Field(
        default=None, validation_alias="JUDGE_3_PROVIDER"
    )
    judge_3_model: str | None = Field(default=None, validation_alias="JUDGE_3_MODEL")
    judge_3_thinking_enabled: bool | None = Field(
        default=None, validation_alias="JUDGE_3_THINKING_ENABLED"
    )
    judge_3_model_family: str | None = Field(
        default=None, validation_alias="JUDGE_3_MODEL_FAMILY"
    )
    judge_3_base_url: str | None = Field(default=None, validation_alias="JUDGE_3_BASE_URL")
    judge_3_api_key: SecretStr | None = Field(default=None, validation_alias="JUDGE_3_API_KEY")
    validator_provider: Literal["miri", "openai_compatible", "paratera"] | None = Field(
        default=None, validation_alias="VALIDATOR_PROVIDER"
    )
    validator_model: str | None = Field(default=None, validation_alias="VALIDATOR_MODEL")
    validator_thinking_enabled: bool | None = Field(
        default=None, validation_alias="VALIDATOR_THINKING_ENABLED"
    )
    validator_base_url: str | None = Field(default=None, validation_alias="VALIDATOR_BASE_URL")
    validator_api_key: SecretStr | None = Field(default=None, validation_alias="VALIDATOR_API_KEY")
    judge_attempt_timeout_seconds: float = Field(
        default=60.0, gt=0, le=60, validation_alias="JUDGE_ATTEMPT_TIMEOUT_SECONDS"
    )
    judge_total_timeout_seconds: float = Field(
        default=110.0, gt=0, le=120, validation_alias="JUDGE_TOTAL_TIMEOUT_SECONDS"
    )
    judge_concurrency_limit: int = Field(
        default=3, ge=1, le=3, validation_alias="JUDGE_CONCURRENCY_LIMIT"
    )
    judge_allow_same_family_development: bool = Field(
        default=False, validation_alias="JUDGE_ALLOW_SAME_FAMILY_DEVELOPMENT"
    )
    judge_allow_search_enabled_development: bool = Field(
        default=False, validation_alias="JUDGE_ALLOW_SEARCH_ENABLED_DEVELOPMENT"
    )
    analysis_total_timeout_seconds: float = Field(
        default=900.0, gt=0, le=1800, validation_alias="ANALYSIS_TOTAL_TIMEOUT_SECONDS"
    )
    analysis_claim_timeout_seconds: float = Field(
        default=420.0, gt=0, le=600, validation_alias="ANALYSIS_CLAIM_TIMEOUT_SECONDS"
    )
    analysis_retrieval_timeout_seconds: float = Field(
        default=180.0, gt=0, le=300, validation_alias="ANALYSIS_RETRIEVAL_TIMEOUT_SECONDS"
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

    @property
    def debug_enabled(self) -> bool:
        """Never expose development diagnostics in staging or production."""

        return self.debug_mode and self.app_env in {"development", "test"}


@lru_cache
def get_settings() -> Settings:
    """Create one immutable settings instance per process."""

    return Settings()


def get_runtime_settings(request: Request) -> Settings:
    """Use the application-factory settings instead of re-reading environment state."""

    return cast(Settings, request.app.state.settings)
