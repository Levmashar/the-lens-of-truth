"""Public contracts for Phase 2 ingestion and atomic-claim extraction."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from app.medical.entities import MedicalEntity
from app.pipeline.claim_types import ClaimType
from app.pipeline.completeness import NormalizationQuality
from app.pipeline.pico import NormalizationStatus, NormalizedPico


class Consent(BaseModel):
    """Versioned acknowledgement required before submitting health-related content."""

    privacy_notice_version: str = Field(min_length=1, max_length=64)
    accepted: Literal[True]


class AnalysisInput(BaseModel):
    """Reference an ephemeral screenshot upload or supply text directly."""

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
        if self.type != "text" and self.text is not None:
            raise ValueError("Only text submissions may include text.")
        if self.type != "screenshot" and self.upload_id is not None:
            raise ValueError("Only screenshot submissions may include upload_id.")
        if self.type != "url" and self.url is not None:
            raise ValueError("Only URL submissions may include url.")
        return self


class CreateAnalysisRequest(BaseModel):
    """Request Phase 2 extraction; later phases extend the same lifecycle."""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal["1.0"] = "1.0"
    client: Literal["web", "wechat", "api"] = "web"
    language: str = Field(default="auto", alias="lang", max_length=16)
    input: AnalysisInput
    consent: Consent


class ScreenshotUploadAccepted(BaseModel):
    """Acknowledgement for a sanitized raw screenshot held for no more than 24 hours."""

    upload_id: UUID
    status: Literal["uploaded"]
    media_type: Literal["image/png"]
    byte_count: int
    width: int
    height: int
    purge_after: datetime


class OcrPreviewLine(BaseModel):
    """One redacted development-preview OCR line with layout metadata."""

    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int


class OcrPreviewResponse(BaseModel):
    """Development-only OCR preview; it never writes recognized text to the database."""

    upload_id: UUID
    provider: str
    language_used: str
    confidence: float | None
    redacted_text: str
    pii_redaction_count: int
    lines: list[OcrPreviewLine]


class ScreenshotOcrMetadata(BaseModel):
    """Safe OCR metadata; recognized text itself is not returned here."""

    provider: str
    confidence: float | None
    pii_redaction_count: int


class ClaimPreviewItem(BaseModel):
    """One transient redacted extraction result, without a persisted claim ID."""

    ordinal: int
    span_start: int
    span_end: int
    raw_text: str
    normalized_text: str | None = None
    claim_type: ClaimType | None = None
    population: str | None = None
    intervention_or_exposure: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    timeframe: str | None = None
    risk_class: str
    verifiability: float | None = None
    coreference_uncertain: bool
    entities: list[MedicalEntity] = Field(default_factory=list)
    pico: NormalizedPico | None = None
    normalization_status: NormalizationStatus = "pending"
    normalization_quality: NormalizationQuality | None = None


class ClaimExtractionPreviewResponse(BaseModel):
    """Development-only extraction output; it does not create database records."""

    input_type: Literal["text", "screenshot"]
    extractor_provider: str
    extractor_model: str | None
    pii_redaction_count: int
    claims: list[ClaimPreviewItem]
    screenshot_ocr: ScreenshotOcrMetadata | None = None


class AnalysisAccepted(BaseModel):
    """A completed Phase 2 extraction, not a medical-evidence result."""

    analysis_id: UUID
    status: Literal["claims_extracted"]
    claim_count: int


class AnalysisClaim(BaseModel):
    """Redacted atomic claim with offsets into the redacted source representation."""

    claim_id: UUID
    ordinal: int
    span_start: int | None
    span_end: int | None
    raw_text: str
    normalized_text: str | None = None
    claim_type: ClaimType | None = None
    population: str | None = None
    intervention_or_exposure: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    timeframe: str | None = None
    risk_class: str
    verifiability: float | None = None
    coreference_uncertain: bool
    resolved_from_span_start: int | None = None
    resolved_from_span_end: int | None = None
    entities: list[MedicalEntity] = Field(default_factory=list)
    pico: NormalizedPico | None = None
    normalization_status: NormalizationStatus = "pending"
    normalization_quality: NormalizationQuality | None = None


class AnalysisDetail(BaseModel):
    """Current Phase 2 state, before retrieval or any medical verdict exists."""

    analysis_id: UUID
    status: Literal["claims_extracted"]
    language: str
    input_type: Literal["text", "screenshot"]
    claims: list[AnalysisClaim]
    screenshot_ocr: ScreenshotOcrMetadata | None = None
    updated_at: datetime
