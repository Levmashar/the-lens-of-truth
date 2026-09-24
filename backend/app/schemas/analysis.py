"""Public API contracts for analysis lifecycle endpoints."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


class Consent(BaseModel):
    """Versioned acknowledgement required before submitting health-related content."""

    privacy_notice_version: str = Field(min_length=1, max_length=64)
    accepted: Literal[True]


class AnalysisInput(BaseModel):
    """Input shape only; ingestion, upload storage, and fetching come later."""

    type: Literal["text", "screenshot", "url"]
    text: str | None = Field(default=None, min_length=1, max_length=20_000)
    upload_id: UUID | None = None
    url: AnyHttpUrl | None = None

    @model_validator(mode="after")
    def validate_input_reference(self) -> "AnalysisInput":
        if self.type == "text" and self.text is None:
            raise ValueError("Text submissions require text.")
        if self.type == "screenshot" and self.upload_id is None:
            raise ValueError("Screenshot submissions require upload_id.")
        if self.type == "url" and self.url is None:
            raise ValueError("URL submissions require url.")
        return self


class CreateAnalysisRequest(BaseModel):
    """Accepted analysis request, designed to remain compatible with later phases."""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal["1.0"] = "1.0"
    client: Literal["web", "wechat", "api"] = "web"
    language: str = Field(default="auto", alias="lang", max_length=16)
    input: AnalysisInput
    consent: Consent


class AnalysisAccepted(BaseModel):
    """Asynchronous acknowledgement; Phase 1 returns this without persistence."""

    analysis_id: UUID
    status: Literal["processing"]
    is_mock: Literal[True] = True


class AnalysisClaim(BaseModel):
    """Placeholder for a future atomic claim response."""

    claim_id: UUID
    raw_text: str
    normalized_text: str | None = None


class AnalysisDetail(BaseModel):
    """Current analysis lifecycle state."""

    analysis_id: UUID
    status: Literal["processing", "complete", "failed"]
    language: str
    claims: list[AnalysisClaim]
    updated_at: datetime
    is_mock: Literal[True] = True

    @classmethod
    def processing(cls, analysis_id: UUID) -> "AnalysisDetail":
        """Build the explicit Phase 1 mock response."""

        return cls(
            analysis_id=analysis_id,
            status="processing",
            language="auto",
            claims=[],
            updated_at=datetime.now(UTC),
        )
