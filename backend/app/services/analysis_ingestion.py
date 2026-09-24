"""Phase 2 orchestration for private ingestion, OCR, and atomic claims."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.claim_extractor import (
    CLAIM_EXTRACTION_PROMPT_VERSION,
    ClaimExtractionPayload,
    ClaimExtractorAdapter,
    validate_claim_candidates,
)
from app.adapters.ocr import TesseractOcrAdapter
from app.adapters.storage import LocalFilesystemUploadStorage
from app.core.errors import LensError
from app.models.claim import Claim
from app.models.enums import InputType
from app.models.screenshot_upload import ScreenshotUpload
from app.models.submission import Submission
from app.schemas.analysis import CreateAnalysisRequest
from app.services.image_ingestion import SanitizedImage
from app.services.redaction import PiiRedactor


@dataclass(frozen=True, slots=True)
class OcrPreviewLine:
    """A redacted OCR line returned only by the development preview endpoint."""

    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class OcrPreview:
    """Ephemeral redacted OCR output; raw recognized text is never persisted."""

    upload_id: UUID
    provider: str
    language_used: str
    confidence: float | None
    redacted_text: str
    pii_redaction_count: int
    lines: tuple[OcrPreviewLine, ...]


@dataclass(frozen=True, slots=True)
class ClaimPreviewItem:
    """One transient, redacted claim-extraction result."""

    ordinal: int
    span_start: int
    span_end: int
    raw_text: str
    normalized_text: str | None
    claim_type: str | None
    population: str | None
    intervention_or_exposure: str | None
    comparator: str | None
    outcome: str | None
    timeframe: str | None
    risk_class: str
    verifiability: float | None
    coreference_uncertain: bool


@dataclass(frozen=True, slots=True)
class ClaimExtractionPreview:
    """Ephemeral extraction output for development diagnostics."""

    input_type: Literal["text", "screenshot"]
    extractor_provider: str
    extractor_model: str | None
    pii_redaction_count: int
    claims: tuple[ClaimPreviewItem, ...]
    screenshot_ocr: tuple[str, float | None] | None


class AnalysisIngestionService:
    """Coordinate only the first pipeline stages; it makes no medical judgment."""

    def __init__(
        self,
        *,
        storage: LocalFilesystemUploadStorage,
        ocr: TesseractOcrAdapter,
        extractor: ClaimExtractorAdapter,
        redactor: PiiRedactor,
        retention_hours: int,
        maximum_claims: int,
        upload_max_bytes: int,
        upload_max_pixels: int,
    ) -> None:
        self._storage = storage
        self._ocr = ocr
        self._extractor = extractor
        self._redactor = redactor
        self._retention_hours = retention_hours
        self._maximum_claims = maximum_claims
        self.upload_max_bytes = upload_max_bytes
        self.upload_max_pixels = upload_max_pixels

    async def create_screenshot_upload(
        self, *, session: Session, image: SanitizedImage
    ) -> ScreenshotUpload:
        """Store a pre-sanitized raw screenshot with a non-extendable purge deadline."""

        await self.purge_expired(session=session)
        now = datetime.now(UTC)
        upload = ScreenshotUpload(
            id=uuid4(),
            object_key="pending",
            content_sha256=image.content_sha256,
            media_type=image.media_type,
            byte_count=image.byte_count,
            width=image.width,
            height=image.height,
            status="uploaded",
            purge_after=now + timedelta(hours=self._retention_hours),
        )
        object_key = await self._storage.put(upload_id=upload.id, content=image.content)
        upload.object_key = object_key
        try:
            session.add(upload)
            session.commit()
            session.refresh(upload)
        except Exception:
            await self._storage.delete(object_key=object_key)
            session.rollback()
            raise
        return upload

    async def create_analysis(
        self, *, session: Session, request: CreateAnalysisRequest
    ) -> Submission:
        """Extract and persist redacted atomic claims from text or a stored screenshot."""

        await self.purge_expired(session=session)
        if request.input.type == "text":
            return await self._create_text_analysis(session=session, request=request)
        if request.input.type == "screenshot":
            return await self._create_screenshot_analysis(session=session, request=request)
        raise LensError(
            status_code=501,
            code="input_type_not_implemented",
            message="URL analysis is not implemented in Phase 2.",
        )

    def get_submission(self, *, session: Session, analysis_id: UUID) -> Submission:
        """Fetch one persisted analysis or return a privacy-safe not-found response."""

        submission = session.get(Submission, analysis_id)
        if submission is None:
            raise LensError(
                status_code=404,
                code="analysis_not_found",
                message="Analysis was not found or has expired.",
            )
        return submission

    async def preview_screenshot_ocr(self, *, session: Session, upload_id: UUID) -> OcrPreview:
        """Re-run OCR for a development preview without retaining recognized text."""

        await self.purge_expired(session=session)
        upload = session.get(ScreenshotUpload, upload_id)
        if upload is None or upload.purge_after <= datetime.now(UTC):
            raise LensError(
                status_code=404,
                code="screenshot_upload_not_found",
                message="Screenshot upload was not found or has expired.",
            )
        result = await self._ocr.recognize(
            image=await self._storage.get(object_key=upload.object_key),
            language_hint="auto",
        )
        redaction = self._redactor.redact(result.text)
        return OcrPreview(
            upload_id=upload.id,
            provider=self._ocr.service_name,
            language_used=result.language_used,
            confidence=result.confidence,
            redacted_text=redaction.text,
            pii_redaction_count=len(redaction.matches),
            lines=tuple(
                OcrPreviewLine(
                    text=self._redactor.redact(line.text).text,
                    confidence=line.confidence,
                    left=line.left,
                    top=line.top,
                    width=line.width,
                    height=line.height,
                )
                for line in result.lines
            ),
        )

    async def preview_claim_extraction(
        self, *, session: Session, request: CreateAnalysisRequest
    ) -> ClaimExtractionPreview:
        """Extract transient redacted claims without creating a submission record."""

        await self.purge_expired(session=session)
        if request.input.type == "text":
            assert request.input.text is not None
            redaction = self._redactor.redact(request.input.text)
            payload = await self._extractor.extract(text=redaction.text, language=request.language)
            return self._claim_preview(
                input_type="text",
                payload=payload,
                redacted_text=redaction.text,
                pii_redaction_count=len(redaction.matches),
                screenshot_ocr=None,
            )
        if request.input.type == "screenshot":
            assert request.input.upload_id is not None
            upload = session.get(ScreenshotUpload, request.input.upload_id)
            if upload is None or upload.purge_after <= datetime.now(UTC):
                raise LensError(
                    status_code=404,
                    code="screenshot_upload_not_found",
                    message="Screenshot upload was not found or has expired.",
                )
            ocr_result = await self._ocr.recognize(
                image=await self._storage.get(object_key=upload.object_key),
                language_hint=request.language,
            )
            if not ocr_result.text.strip():
                raise LensError(
                    status_code=422,
                    code="screenshot_text_not_found",
                    message="No readable text was found in the screenshot.",
                )
            redaction = self._redactor.redact(ocr_result.text)
            payload = await self._extractor.extract(text=redaction.text, language=request.language)
            return self._claim_preview(
                input_type="screenshot",
                payload=payload,
                redacted_text=redaction.text,
                pii_redaction_count=len(redaction.matches),
                screenshot_ocr=(self._ocr.service_name, ocr_result.confidence),
            )
        raise LensError(
            status_code=501,
            code="input_type_not_implemented",
            message="URL analysis is not implemented in Phase 2.",
        )

    async def purge_expired(self, *, session: Session) -> int:
        """Delete expired raw assets and their short-lived analysis records."""

        now = datetime.now(UTC)
        uploads = list(
            session.scalars(select(ScreenshotUpload).where(ScreenshotUpload.purge_after <= now))
        )
        for upload in uploads:
            await self._storage.delete(object_key=upload.object_key)
            session.delete(upload)

        submissions = list(session.scalars(select(Submission).where(Submission.purge_after <= now)))
        for submission in submissions:
            session.delete(submission)
        if uploads or submissions:
            session.commit()
        return len(uploads) + len(submissions)

    async def _create_text_analysis(
        self, *, session: Session, request: CreateAnalysisRequest
    ) -> Submission:
        assert request.input.text is not None
        raw_text = request.input.text
        redaction = self._redactor.redact(raw_text)
        payload = await self._extractor.extract(text=redaction.text, language=request.language)
        return self._persist_submission(
            session=session,
            request=request,
            content_sha256=_sha256(raw_text),
            candidates=payload,
            redacted_text=redaction.text,
        )

    async def _create_screenshot_analysis(
        self, *, session: Session, request: CreateAnalysisRequest
    ) -> Submission:
        assert request.input.upload_id is not None
        upload = session.get(ScreenshotUpload, request.input.upload_id)
        if upload is None or upload.purge_after <= datetime.now(UTC):
            raise LensError(
                status_code=404,
                code="screenshot_upload_not_found",
                message="Screenshot upload was not found or has expired.",
            )
        if upload.submission_id is not None:
            raise LensError(
                status_code=409,
                code="screenshot_upload_already_used",
                message="Screenshot upload has already been submitted for analysis.",
            )

        ocr_result = await self._ocr.recognize(
            image=await self._storage.get(object_key=upload.object_key),
            language_hint=request.language,
        )
        if not ocr_result.text.strip():
            raise LensError(
                status_code=422,
                code="screenshot_text_not_found",
                message="No readable text was found in the screenshot.",
            )
        redaction = self._redactor.redact(ocr_result.text)
        payload = await self._extractor.extract(text=redaction.text, language=request.language)
        submission = self._persist_submission(
            session=session,
            request=request,
            content_sha256=upload.content_sha256,
            candidates=payload,
            redacted_text=redaction.text,
            screenshot_upload=upload,
        )
        upload.ocr_provider = self._ocr.service_name
        upload.ocr_confidence = ocr_result.confidence
        upload.pii_redaction_count = len(redaction.matches)
        upload.status = "processed"
        session.commit()
        session.refresh(submission)
        return submission

    def _persist_submission(
        self,
        *,
        session: Session,
        request: CreateAnalysisRequest,
        content_sha256: str,
        candidates: ClaimExtractionPayload,
        redacted_text: str,
        screenshot_upload: ScreenshotUpload | None = None,
    ) -> Submission:
        verified_candidates = validate_claim_candidates(
            payload=candidates,
            source_text=redacted_text,
            maximum_claims=self._maximum_claims,
        )
        submission = Submission(
            id=uuid4(),
            client=request.client,
            language=request.language,
            input_type=InputType(request.input.type),
            content_sha256=content_sha256,
            privacy_notice_version=request.consent.privacy_notice_version,
            consent_accepted=request.consent.accepted,
            status="claims_extracted",
            extraction_provider=self._extractor.service_name,
            extraction_model=self._extractor.model_id,
            extraction_prompt_version=CLAIM_EXTRACTION_PROMPT_VERSION,
            purge_after=datetime.now(UTC) + timedelta(hours=self._retention_hours),
        )
        def safe_pico(value: str | None) -> str | None:
            return self._redactor.redact(value).text if value else None

        for ordinal, candidate in enumerate(verified_candidates, start=1):
            normalized = candidate.normalized_claim
            safe_normalized = self._redactor.redact(normalized).text if normalized else None
            pico = candidate.pico
            submission.claims.append(
                Claim(
                    ordinal=ordinal,
                    span_start=candidate.span_start,
                    span_end=candidate.span_end,
                    raw_text=redacted_text[candidate.span_start : candidate.span_end],
                    normalized_text=safe_normalized,
                    claim_type=candidate.claim_type,
                    population=safe_pico(pico.population) if pico else None,
                    intervention_or_exposure=(
                        safe_pico(pico.intervention_or_exposure) if pico else None
                    ),
                    comparator=safe_pico(pico.comparator) if pico else None,
                    outcome=safe_pico(pico.outcome) if pico else None,
                    timeframe=safe_pico(pico.timeframe) if pico else None,
                    risk_class=candidate.risk_class,
                    verifiability=candidate.verifiability,
                    coreference_uncertain=candidate.coreference_uncertain,
                    resolved_from_span_start=candidate.resolved_from_span_start,
                    resolved_from_span_end=candidate.resolved_from_span_end,
                )
            )
        if screenshot_upload is not None:
            screenshot_upload.submission = submission
        session.add(submission)
        session.commit()
        session.refresh(submission)
        return submission

    def _claim_preview(
        self,
        *,
        input_type: Literal["text", "screenshot"],
        payload: ClaimExtractionPayload,
        redacted_text: str,
        pii_redaction_count: int,
        screenshot_ocr: tuple[str, float | None] | None,
    ) -> ClaimExtractionPreview:
        """Build response-safe preview fields from locally verified model output."""

        candidates = validate_claim_candidates(
            payload=payload,
            source_text=redacted_text,
            maximum_claims=self._maximum_claims,
        )

        def redact(value: str | None) -> str | None:
            return self._redactor.redact(value).text if value else None

        return ClaimExtractionPreview(
            input_type=input_type,
            extractor_provider=self._extractor.service_name,
            extractor_model=self._extractor.model_id,
            pii_redaction_count=pii_redaction_count,
            claims=tuple(
                ClaimPreviewItem(
                    ordinal=ordinal,
                    span_start=candidate.span_start,
                    span_end=candidate.span_end,
                    raw_text=redacted_text[candidate.span_start : candidate.span_end],
                    normalized_text=redact(candidate.normalized_claim),
                    claim_type=candidate.claim_type,
                    population=redact(candidate.pico.population) if candidate.pico else None,
                    intervention_or_exposure=(
                        redact(candidate.pico.intervention_or_exposure) if candidate.pico else None
                    ),
                    comparator=redact(candidate.pico.comparator) if candidate.pico else None,
                    outcome=redact(candidate.pico.outcome) if candidate.pico else None,
                    timeframe=redact(candidate.pico.timeframe) if candidate.pico else None,
                    risk_class=candidate.risk_class,
                    verifiability=candidate.verifiability,
                    coreference_uncertain=candidate.coreference_uncertain,
                )
                for ordinal, candidate in enumerate(candidates, start=1)
            ),
            screenshot_ocr=screenshot_ocr,
        )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
