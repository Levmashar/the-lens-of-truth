"""Analysis routes for intake, atomic claims, and medical normalization."""

import json
from collections.abc import AsyncIterator
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.adapters.pubmed import PubMedAdapter
from app.core.config import Settings, get_runtime_settings
from app.core.errors import LensError
from app.db.session import get_db_session
from app.dependencies import get_analysis_ingestion_service, get_pubmed_adapter
from app.medical.entities import MedicalEntity
from app.models.claim import Claim
from app.models.screenshot_upload import ScreenshotUpload
from app.models.submission import Submission
from app.pipeline.claim_types import legacy_claim_type
from app.pipeline.completeness import NormalizationQuality
from app.pipeline.pico import NormalizationStatus, NormalizedPico
from app.retrieval.claims import snapshot_claim
from app.retrieval.persistence import persist_retrieval
from app.retrieval.service import retrieve_pubmed
from app.schemas.analysis import (
    AnalysisAccepted,
    AnalysisClaim,
    AnalysisDetail,
    ClaimExtractionPreviewResponse,
    ClaimPreviewItem,
    CreateAnalysisRequest,
    OcrPreviewLine,
    OcrPreviewResponse,
    ScreenshotOcrMetadata,
    ScreenshotUploadAccepted,
)
from app.schemas.retrieval import EvidencePreviewRequest, EvidencePreviewResponse
from app.services.analysis_ingestion import AnalysisIngestionService
from app.services.image_ingestion import ScreenshotSanitizer

router = APIRouter()
_status_adapter: TypeAdapter[NormalizationStatus] = TypeAdapter(NormalizationStatus)


@router.post("/evidence-preview", response_model=EvidencePreviewResponse)
async def preview_pubmed_evidence(
    request: EvidencePreviewRequest,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AnalysisIngestionService, Depends(get_analysis_ingestion_service)],
    adapter: Annotated[PubMedAdapter, Depends(get_pubmed_adapter)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> EvidencePreviewResponse:
    """Retrieve PubMed evidence for one stored claim; never produce a verdict."""

    if settings.app_env not in {"development", "test"}:
        raise LensError(404, "evidence_preview_not_available",
                        "Evidence preview is not available in this environment.")
    service.get_submission(session=session, analysis_id=request.analysis_id)
    claim = session.get(Claim, request.claim_id)
    if claim is None or claim.submission_id != request.analysis_id:
        raise LensError(404, "claim_not_found", "Claim was not found or has expired.")
    result = await retrieve_pubmed(snapshot_claim(claim), adapter)
    persist_retrieval(session, result)
    return EvidencePreviewResponse(evidence_pack=result.pack, diagnostics=result.diagnostics)


@router.post(
    "/uploads/screenshots",
    response_model=ScreenshotUploadAccepted,
    status_code=status.HTTP_201_CREATED,
)
async def create_screenshot_upload(
    screenshot: Annotated[UploadFile, File(description="PNG, JPEG, or WebP screenshot")],
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AnalysisIngestionService, Depends(get_analysis_ingestion_service)],
) -> ScreenshotUploadAccepted:
    """Accept one sanitized screenshot before it is referenced by an analysis."""

    sanitizer = ScreenshotSanitizer(
        max_bytes=service.upload_max_bytes,
        max_pixels=service.upload_max_pixels,
    )
    image = await sanitizer.sanitize_upload(screenshot)
    upload = await service.create_screenshot_upload(session=session, image=image)
    return _upload_response(upload)


@router.post(
    "/uploads/screenshots/{upload_id}/ocr-preview",
    response_model=OcrPreviewResponse,
)
async def preview_screenshot_ocr(
    upload_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AnalysisIngestionService, Depends(get_analysis_ingestion_service)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> OcrPreviewResponse:
    """Expose redacted OCR diagnostics only in development/test environments."""

    if settings.app_env not in {"development", "test"}:
        raise LensError(
            status_code=404,
            code="ocr_preview_not_available",
            message="OCR preview is not available in this environment.",
        )
    preview = await service.preview_screenshot_ocr(session=session, upload_id=upload_id)
    return OcrPreviewResponse(
        upload_id=preview.upload_id,
        provider=preview.provider,
        language_used=preview.language_used,
        confidence=preview.confidence,
        redacted_text=preview.redacted_text,
        pii_redaction_count=preview.pii_redaction_count,
        lines=[
            OcrPreviewLine(
                text=line.text,
                confidence=line.confidence,
                left=line.left,
                top=line.top,
                width=line.width,
                height=line.height,
            )
            for line in preview.lines
        ],
    )


@router.post("/claim-preview", response_model=ClaimExtractionPreviewResponse)
async def preview_claim_extraction(
    request: CreateAnalysisRequest,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AnalysisIngestionService, Depends(get_analysis_ingestion_service)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> ClaimExtractionPreviewResponse:
    """Return redacted AI extraction output only in development and test environments."""

    if settings.app_env not in {"development", "test"}:
        raise LensError(
            status_code=404,
            code="claim_preview_not_available",
            message="Claim extraction preview is not available in this environment.",
        )
    preview = await service.preview_claim_extraction(session=session, request=request)
    screenshot_ocr = None
    if preview.screenshot_ocr is not None:
        provider, confidence = preview.screenshot_ocr
        screenshot_ocr = ScreenshotOcrMetadata(
            provider=provider,
            confidence=confidence,
            pii_redaction_count=preview.pii_redaction_count,
        )
    return ClaimExtractionPreviewResponse(
        input_type=preview.input_type,
        extractor_provider=preview.extractor_provider,
        extractor_model=preview.extractor_model,
        pii_redaction_count=preview.pii_redaction_count,
        claims=[
            ClaimPreviewItem(
                ordinal=claim.ordinal,
                span_start=claim.span_start,
                span_end=claim.span_end,
                raw_text=claim.raw_text,
                normalized_text=claim.normalized_text,
                claim_type=claim.claim_type,
                population=claim.population,
                intervention_or_exposure=claim.intervention_or_exposure,
                comparator=claim.comparator,
                outcome=claim.outcome,
                timeframe=claim.timeframe,
                risk_class=claim.risk_class,
                verifiability=claim.verifiability,
                coreference_uncertain=claim.coreference_uncertain,
                entities=list(claim.entities),
                pico=claim.pico,
                normalization_status=claim.normalization_status,
                normalization_quality=claim.normalization_quality,
            )
            for claim in preview.claims
        ],
        screenshot_ocr=screenshot_ocr,
    )


@router.post("", response_model=AnalysisAccepted, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    request: CreateAnalysisRequest,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AnalysisIngestionService, Depends(get_analysis_ingestion_service)],
    _idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AnalysisAccepted:
    """Run only ingestion, OCR when needed, redaction, and claim extraction."""

    submission = await service.create_analysis(session=session, request=request)
    return AnalysisAccepted(
        analysis_id=submission.id,
        status="claims_extracted",
        claim_count=len(submission.claims),
    )


@router.get("/{analysis_id}", response_model=AnalysisDetail)
async def get_analysis(
    analysis_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AnalysisIngestionService, Depends(get_analysis_ingestion_service)],
) -> AnalysisDetail:
    """Return persisted redacted claims and safe OCR metadata for one analysis."""

    return _analysis_detail(service.get_submission(session=session, analysis_id=analysis_id))


async def _analysis_events(submission: Submission) -> AsyncIterator[str]:
    """Emit completed Phase 2 stages, never simulated pipeline progress."""

    stages = [{"stage": "ingested", "progress": 0.25}]
    if submission.input_type.value == "screenshot":
        stages.extend(
            [
                {"stage": "ocr_complete", "progress": 0.55},
                {"stage": "pii_redaction_complete", "progress": 0.7},
            ]
        )
    else:
        stages.append({"stage": "pii_redaction_complete", "progress": 0.55})
    stages.append({"stage": "claims_extracted", "progress": 1.0})
    for event in stages:
        yield f"event: stage\ndata: {json.dumps(event)}\n\n"
    yield f"event: completed\ndata: {json.dumps({'analysis_id': str(submission.id)})}\n\n"


@router.get("/{analysis_id}/events")
async def get_analysis_events(
    analysis_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AnalysisIngestionService, Depends(get_analysis_ingestion_service)],
) -> StreamingResponse:
    """Expose a server-sent snapshot of the completed Phase 2 stages."""

    submission = service.get_submission(session=session, analysis_id=analysis_id)
    return StreamingResponse(_analysis_events(submission), media_type="text/event-stream")


def _upload_response(upload: ScreenshotUpload) -> ScreenshotUploadAccepted:
    return ScreenshotUploadAccepted(
        upload_id=upload.id,
        status="uploaded",
        media_type="image/png",
        byte_count=upload.byte_count,
        width=upload.width,
        height=upload.height,
        purge_after=upload.purge_after,
    )


def _analysis_detail(submission: Submission) -> AnalysisDetail:
    screenshot_ocr = None
    if submission.screenshot_upload is not None:
        upload = submission.screenshot_upload
        screenshot_ocr = ScreenshotOcrMetadata(
            provider=upload.ocr_provider or "unknown",
            confidence=upload.ocr_confidence,
            pii_redaction_count=upload.pii_redaction_count or 0,
        )
    input_type: Literal["text", "screenshot"] = (
        "screenshot" if submission.input_type.value == "screenshot" else "text"
    )
    return AnalysisDetail(
        analysis_id=submission.id,
        status="claims_extracted",
        language=submission.language,
        input_type=input_type,
        claims=[
            AnalysisClaim(
                claim_id=claim.id,
                ordinal=claim.ordinal,
                span_start=claim.span_start,
                span_end=claim.span_end,
                raw_text=claim.raw_text,
                normalized_text=claim.normalized_text,
                claim_type=legacy_claim_type(claim.claim_type),
                population=claim.population,
                intervention_or_exposure=claim.intervention_or_exposure,
                comparator=claim.comparator,
                outcome=claim.outcome,
                timeframe=claim.timeframe,
                risk_class=claim.risk_class,
                verifiability=claim.verifiability,
                coreference_uncertain=claim.coreference_uncertain,
                resolved_from_span_start=claim.resolved_from_span_start,
                resolved_from_span_end=claim.resolved_from_span_end,
                entities=[
                    MedicalEntity.model_validate(entity) for entity in claim.linked_entities or []
                ],
                pico=(NormalizedPico.model_validate(claim.pico_json) if claim.pico_json else None),
                normalization_status=_status_adapter.validate_python(claim.normalization_status),
                normalization_quality=(
                    NormalizationQuality.model_validate(claim.normalization_quality)
                    if claim.normalization_quality else None
                ),
            )
            for claim in sorted(submission.claims, key=lambda value: value.ordinal)
        ],
        screenshot_ocr=screenshot_ocr,
        updated_at=submission.updated_at,
    )
