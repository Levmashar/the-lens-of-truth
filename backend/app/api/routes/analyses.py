"""Analysis routes for intake, atomic claims, and medical normalization."""

import hashlib
import json
from collections.abc import AsyncIterator
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from app.adapters.crossref import CrossrefAdapter
from app.adapters.pubmed import PubMedAdapter
from app.core.config import Settings, get_runtime_settings
from app.core.debug_trace import model_events
from app.core.errors import LensError
from app.db.session import get_db_session
from app.dependencies import (
    get_analysis_ingestion_service,
    get_crossref_adapter,
    get_pubmed_adapter,
)
from app.medical.entities import MedicalEntity
from app.models.analysis_run import AnalysisRunRecord, ClaimAnalysisRunRecord
from app.models.claim import Claim
from app.models.judge_run import JudgeRunRecord
from app.models.judge_validation_run import JudgeValidationRunRecord
from app.models.report_run import ReportRunRecord
from app.models.retrieval import EvidencePackRecord
from app.models.screenshot_upload import ScreenshotUpload
from app.models.submission import Submission
from app.models.verdict_run import VerdictRunRecord
from app.orchestration.state import claim_runs, get_run, start_analysis
from app.orchestration.worker import run_background
from app.pipeline.claim_types import legacy_claim_type
from app.pipeline.completeness import NormalizationQuality
from app.pipeline.pico import NormalizationStatus, NormalizedPico
from app.report.builder import semantic_report_hash
from app.report.models import LensReport
from app.retrieval.claims import snapshot_claim
from app.retrieval.evidence_pack import canonical_pack_bytes
from app.retrieval.models import EvidencePack
from app.retrieval.persistence import persist_retrieval
from app.retrieval.service import retrieve_pubmed
from app.schemas.analysis import (
    AnalysisClaim,
    AnalysisClaimsResponse,
    AnalysisDetail,
    AnalysisProgress,
    AnalysisStarted,
    ClaimAnalysisSummary,
    ClaimExtractionPreviewResponse,
    ClaimPreviewItem,
    CreateAnalysisRequest,
    DebugJudgeRun,
    DebugModelEvent,
    DebugModelStatus,
    OcrPreviewLine,
    OcrPreviewResponse,
    ScreenshotOcrMetadata,
    ScreenshotUploadAccepted,
)
from app.schemas.retrieval import EvidencePreviewRequest, EvidencePreviewResponse
from app.services.analysis_ingestion import AnalysisIngestionService
from app.services.image_ingestion import ScreenshotSanitizer
from app.verdict.models import LensVerdict

router = APIRouter()
_status_adapter: TypeAdapter[NormalizationStatus] = TypeAdapter(NormalizationStatus)


@router.post("/evidence-preview", response_model=EvidencePreviewResponse)
async def preview_pubmed_evidence(
    request: EvidencePreviewRequest,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AnalysisIngestionService, Depends(get_analysis_ingestion_service)],
    adapter: Annotated[PubMedAdapter, Depends(get_pubmed_adapter)],
    crossref: Annotated[CrossrefAdapter | None, Depends(get_crossref_adapter)],
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
    result = await retrieve_pubmed(
        snapshot_claim(claim), adapter,
        selected_limit=settings.pubmed_selected_evidence_limit,
        max_per_document=settings.pubmed_max_passages_per_document,
        crossref=crossref,
        crossref_total_timeout_seconds=settings.crossref_total_timeout_seconds,
    )
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
                standalone_status=claim.standalone_status,
                resolved_from_span_start=claim.resolved_from_span_start,
                resolved_from_span_end=claim.resolved_from_span_end,
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


@router.post("", response_model=AnalysisStarted, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    request: CreateAnalysisRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AnalysisStarted:
    """Reserve a durable run and return before extraction or external calls."""

    run, created = start_analysis(
        session, request, idempotency_key=idempotency_key,
        retention_hours=settings.upload_retention_hours,
    )
    if created:
        background_tasks.add_task(run_background, run.id, request, settings)
    return AnalysisStarted(
        analysis_id=run.id, status=cast(Literal[
            "queued", "running", "completed", "failed", "partially_completed",
        ], run.status), stage=run.stage,
        claim_count=run.claim_count, completed_claims=run.completed_claims,
    )


@router.get("/{analysis_id}", response_model=AnalysisProgress | AnalysisDetail)
async def get_analysis(
    analysis_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AnalysisIngestionService, Depends(get_analysis_ingestion_service)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> AnalysisProgress | AnalysisDetail:
    """Return durable progress and any persisted redacted claims."""

    run = session.get(AnalysisRunRecord, analysis_id)
    if run is None:
        return _analysis_detail(service.get_submission(session=session, analysis_id=analysis_id))
    get_run(session, analysis_id)
    claims = []
    detail: AnalysisDetail | None = None
    if run.submission_id is not None:
        submission = service.get_submission(session=session, analysis_id=run.submission_id)
        detail = _analysis_detail(submission)
        claims = detail.claims
    debug_events = (
        [DebugModelEvent.model_validate(item) for item in model_events(run.id)]
        if settings.debug_enabled else None
    )
    return AnalysisProgress(
        analysis_id=run.id, status=cast(Literal[
            "queued", "running", "completed", "failed", "partially_completed",
        ], run.status), stage=run.stage,
        completed_stages=run.completed_stages, claim_count=run.claim_count,
        stage_timestamps=run.stage_timestamps,
        completed_claims=run.completed_claims, failure_code=run.failure_code,
        language=detail.language if detail else None,
        input_type=detail.input_type if detail else None,
        claims=claims, screenshot_ocr=detail.screenshot_ocr if detail else None,
        updated_at=run.updated_at, debug_enabled=settings.debug_enabled,
        debug_events=debug_events,
        debug_models=_debug_model_statuses(settings, debug_events)
        if debug_events is not None else None,
    )


def _debug_model_statuses(
    settings: Settings, events: list[DebugModelEvent],
) -> list[DebugModelStatus]:
    configured = [
        ("extraction", settings.claim_extractor_provider, settings.claim_extractor_model),
        ("judge_1", settings.judge_1_provider, settings.judge_1_model),
        ("judge_2", settings.judge_2_provider, settings.judge_2_model),
        ("judge_3", settings.judge_3_provider, settings.judge_3_model),
    ]
    statuses: list[DebugModelStatus] = []
    for role, provider, model in configured:
        if not model:
            continue
        last = next(
            (event for event in reversed(events)
             if event.role == role and event.model == model), None,
        )
        statuses.append(DebugModelStatus(
            role=role, provider=provider or "unconfigured", model=model,
            status=last.status if last else "not_called",
            failure_type=last.failure_type if last else None,
        ))
    return statuses


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
    """Emit one safe progress snapshot; clients poll GET for ongoing work."""

    run = session.get(AnalysisRunRecord, analysis_id)
    if run is None:
        submission = service.get_submission(session=session, analysis_id=analysis_id)
        return StreamingResponse(_analysis_events(submission), media_type="text/event-stream")
    get_run(session, analysis_id)
    payload = {
        "analysis_id": str(run.id), "status": run.status, "stage": run.stage,
        "completed_stages": run.completed_stages, "claim_count": run.claim_count,
        "completed_claims": run.completed_claims,
    }

    async def snapshot() -> AsyncIterator[str]:
        yield f"event: analysis.progress\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(snapshot(), media_type="text/event-stream")


@router.get("/{analysis_id}/claims", response_model=AnalysisClaimsResponse)
async def get_analysis_claims(
    analysis_id: UUID, session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> AnalysisClaimsResponse:
    """Return claim-scoped checkpoint IDs, not a blended medical result."""

    get_run(session, analysis_id)
    summaries = []
    for row in claim_runs(session, analysis_id):
        verdict = session.get(VerdictRunRecord, row.verdict_run_id) if row.verdict_run_id else None
        summaries.append(ClaimAnalysisSummary(
            claim_id=row.claim_id, ordinal=row.ordinal, status=row.status,
            stage=row.stage, completed_stages=row.completed_stages,
            stage_timestamps=row.stage_timestamps,
            failure_code=row.failure_code,
            evidence_pack_id=row.evidence_pack_id, evidence_pack_hash=row.evidence_pack_hash,
            judge_run_ids=[UUID(item) for item in row.judge_run_ids],
            judge_validation_run_ids=[UUID(item) for item in row.validation_run_ids],
            verdict_run_id=row.verdict_run_id, report_run_id=row.report_run_id,
            production_qualified=verdict.production_qualified if verdict else None,
            result_label=(LensVerdict(verdict.verdict) if verdict and (
                settings.app_env not in {"staging", "production"}
                or verdict.production_qualified
            ) else None),
            debug_judge_runs=(
                _debug_judge_runs(session, row) if settings.debug_enabled else None
            ),
        ))
    return AnalysisClaimsResponse(analysis_id=analysis_id, claims=summaries)


def _debug_judge_runs(
    session: Session, row: ClaimAnalysisRunRecord,
) -> list[DebugJudgeRun]:
    """Read only allowlisted audit metadata; never expose prompts or responses."""

    validations: dict[UUID, JudgeValidationRunRecord] = {}
    for raw_id in row.validation_run_ids:
        validation = session.get(JudgeValidationRunRecord, UUID(raw_id))
        if validation is not None:
            validations[validation.judge_run_id] = validation
    summaries: list[DebugJudgeRun] = []
    for raw_id in row.judge_run_ids:
        judge = session.get(JudgeRunRecord, UUID(raw_id))
        if judge is None or judge.claim_id != row.claim_id:
            continue
        validation = validations.get(judge.id)
        summaries.append(DebugJudgeRun(
            slot=judge.slot, provider=judge.provider, model=judge.model,
            model_family=judge.model_family, outcome_status=judge.outcome_status,
            error_category=judge.error_category, attempt_count=judge.attempt_count,
            latency_ms=judge.latency_ms,
            validation_status=validation.status if validation else None,
            validation_error_category=validation.error_category if validation else None,
        ))
    return summaries


@router.get("/{analysis_id}/claims/{claim_id}/report", response_model=LensReport)
async def get_claim_report(
    analysis_id: UUID, claim_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> LensReport:
    """Serve only the named frozen report; never rebuild or fetch on read."""

    get_run(session, analysis_id)
    row = next((item for item in claim_runs(session, analysis_id)
                if item.claim_id == claim_id), None)
    if row is None or row.report_run_id is None:
        raise LensError(404, "report_not_found", "Report is not available.")
    record = session.get(ReportRunRecord, row.report_run_id)
    if record is None:
        raise LensError(404, "report_not_found", "Report is not available.")
    try:
        report = LensReport.model_validate(record.result_json)
        pack = session.get(EvidencePackRecord, row.evidence_pack_id)
        verdict = session.get(VerdictRunRecord, row.verdict_run_id)
        frozen_pack = EvidencePack.model_validate(pack.snapshot_json) if pack else None
        actual_pack_hash = (hashlib.sha256(canonical_pack_bytes(
            frozen_pack.claim_snapshot, frozen_pack.query_plan,
            frozen_pack.documents, frozen_pack.passages,
            frozen_pack.selected_evidence_ids,
            pack_version=frozen_pack.evidence_pack_version,
        )).hexdigest() if frozen_pack else None)
        valid = (
            pack is not None and pack.claim_id == claim_id
            and frozen_pack is not None and frozen_pack.claim_id == claim_id
            and frozen_pack.claim_snapshot.claim_id == claim_id
            and pack.version == frozen_pack.evidence_pack_version
            and frozen_pack.snapshot_hash == actual_pack_hash
            and pack.snapshot_hash == actual_pack_hash
            and pack.snapshot_hash == row.evidence_pack_hash
            and verdict is not None and verdict.claim_id == claim_id
            and verdict.evidence_pack_id == pack.id
            and verdict.semantic_hash == report.provenance.verdict_semantic_hash
            and verdict.production_qualified == report.production_qualified
            and record.id == row.report_run_id
            and record.verdict_run_id == row.verdict_run_id == report.verdict_run_id
            and record.semantic_hash == report.semantic_hash == semantic_report_hash(report)
            and record.report_version == report.report_version
            and record.report_builder_version == report.provenance.report_builder_version
            and record.production_qualified == report.production_qualified
            and report.provenance.evidence_pack_id == row.evidence_pack_id
            and report.provenance.evidence_pack_hash == row.evidence_pack_hash
            and set(report.provenance.judge_run_ids) == set(map(UUID, row.judge_run_ids))
            and len(report.provenance.judge_run_ids) == len(row.judge_run_ids)
            and set(report.provenance.judge_validation_run_ids) == set(
                map(UUID, row.validation_run_ids)
            )
            and len(report.provenance.judge_validation_run_ids) == len(row.validation_run_ids)
        )
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise LensError(503, "report_provenance_invalid", "Report provenance is unavailable.")
    if settings.app_env in {"staging", "production"} and not report.production_qualified:
        raise LensError(403, "report_not_qualified",
                        "This report is not qualified for public release.")
    return report


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
                standalone_status=claim.standalone_status,
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
