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
    get_authoritative_adapter,
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
from app.report.reading_guide import ReportReadingGuide, build_reading_guide
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
    DebugNumericFinding,
    OcrPreviewLine,
    OcrPreviewResponse,
    ScreenshotOcrMetadata,
    ScreenshotReadRequest,
    ScreenshotTextResponse,
    ScreenshotUploadAccepted,
)
from app.schemas.retrieval import EvidencePreviewRequest, EvidencePreviewResponse
from app.services.analysis_ingestion import AnalysisIngestionService
from app.services.image_ingestion import ScreenshotSanitizer
from app.validation.models import JudgeValidationResult
from app.verdict.models import AggregationInput, LensVerdict, VerdictResult
from app.verdict.persistence import load_aggregation_context
from app.verdict.service import semantic_result_hash

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
        authoritative=get_authoritative_adapter(settings),
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
    "/uploads/screenshots/{upload_id}/read",
    response_model=ScreenshotTextResponse,
)
async def read_screenshot_text(
    upload_id: UUID,
    request: ScreenshotReadRequest,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AnalysisIngestionService, Depends(get_analysis_ingestion_service)],
) -> ScreenshotTextResponse:
    """Run local OCR for review without extraction, retrieval, or judging."""

    result = await service.read_screenshot_text(
        session=session, upload_id=upload_id, language=request.language,
    )
    return ScreenshotTextResponse(
        upload_id=result.upload_id,
        redacted_text=result.redacted_text,
        confidence=result.confidence,
        language_used=result.language_used,
    )


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
        document_mode=run.stage_timestamps.get("document", {}).get("mode") == "document",
        debug_events=debug_events,
        debug_models=_debug_model_statuses(settings, debug_events, session, run)
        if debug_events is not None else None,
    )


@router.get("/{analysis_id}/document")
async def get_document_report(
    analysis_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> dict[str, object]:
    """Read the saved overview only; GET never invokes a model or retrieval."""
    from app.document.audit import verify_document_report
    from app.document.models import DocumentPlan
    from app.document.persistence import latest_document_artifact, load_document_artifacts
    from app.document.report import build_document_report

    get_run(session, analysis_id)
    try:
        artifact = latest_document_artifact(session, analysis_id, "report")
        if artifact is None:
            raise LensError(404, "document_not_ready", "Document checks are being prepared.")
        report = dict(artifact.snapshot_json)
        if settings.app_env in {"staging", "production"} and not report.get("production_qualified"):
            raise LensError(403, "report_not_qualified",
                            "Report is not qualified for public release.")
        plan_row = latest_document_artifact(session, analysis_id, "plan")
        if plan_row is None:
            raise ValueError("Document plan is absent")
        parents = [row for row in load_document_artifacts(session, analysis_id)
                   if row.created_at <= artifact.created_at]
        evidence_rows = [row for row in parents if row.kind == "group_evidence"]
        judge_rows = [row for row in parents if row.kind == "group_judge"]
        verify_document_report(report, plan_row, evidence_rows, judge_rows,
                               analysis_id, settings.app_env)
        evidence = {row.group_id: row.snapshot_json for row in evidence_rows if row.group_id}
        runs: dict[str, list[dict[str, object]]] = {}
        for row in judge_rows:
            if row.group_id is None:
                raise ValueError("Document judge group is absent")
            runs.setdefault(row.group_id, []).append(row.snapshot_json)
        failures = {row.group_id: str(row.snapshot_json["failure"]) for row in parents
                    if row.kind == "error" and row.group_id}
        projection = build_document_report(
            analysis_id, DocumentPlan.model_validate(plan_row.snapshot_json), evidence, runs,
            app_env=settings.app_env, status=str(report["status"]), failures=failures,
        )
        if projection != report:
            raise ValueError("Document report projection mismatch")
        if settings.debug_enabled:
            # Exact grouped responses and timing; prompts/keys are never returned.
            report["debug_group_runs"] = [
                {k: v for k, v in row.snapshot_json.items()
                 if k not in {"group_input", "validation_input"}}
                for row in judge_rows]
            report["debug_errors"] = [row.snapshot_json for row in parents if row.kind == "error"]
        return report
    except (ValueError, TypeError, KeyError) as exc:
        raise LensError(503, "document_audit_invalid",
                        "Document audit could not be verified.") from exc


def _debug_model_statuses(
    settings: Settings, events: list[DebugModelEvent], session: Session,
    run: AnalysisRunRecord,
) -> list[DebugModelStatus]:
    """Prefer this analysis's persisted model identity over today's settings."""

    actual: dict[str, tuple[str, str, str, str | None]] = {}
    audited_validators: dict[tuple[str, str, str], tuple[str, str | None]] = {}
    if run.submission_id is not None:
        submission = session.get(Submission, run.submission_id)
        if submission is not None and submission.extraction_model:
            actual["extraction"] = (
                submission.extraction_provider or "unconfigured",
                submission.extraction_model, "responded", None,
            )
    for claim_row in claim_runs(session, run.id):
        for judge_id in claim_row.judge_run_ids:
            judge = session.get(JudgeRunRecord, UUID(judge_id))
            if judge is not None and judge.claim_id == claim_row.claim_id:
                actual[f"judge_{judge.slot}"] = (
                    judge.provider, judge.model,
                    "responded" if judge.outcome_status == "succeeded" else "unavailable",
                    judge.error_category,
                )
        for validation_id in claim_row.validation_run_ids or ():
            validation = session.get(JudgeValidationRunRecord, UUID(validation_id))
            if (validation is None or not validation.entailment_provider
                    or not validation.entailment_model or not validation.attempt_count):
                continue
            role = ("semantic_validator" if validation.validation_version !=
                    "judge-validation-1.0" else "citation_validator")
            failure = validation.error_category
            unavailable = failure in {
                "joint_axes_timeout", "joint_axes_validator_unavailable",
                "source_id_contract_error",
                "joint_validator_unavailable", "entailment_provider_error",
            }
            audited_validators[(role, validation.entailment_provider,
                                validation.entailment_model)] = (
                "unavailable" if unavailable else "responded", failure if unavailable else None,
            )
    configured = [
        ("extraction", settings.claim_extractor_provider, settings.claim_extractor_model),
        ("judge_1", settings.judge_1_provider, settings.judge_1_model),
        ("judge_2", settings.judge_2_provider, settings.judge_2_model),
        ("judge_3", settings.judge_3_provider, settings.judge_3_model),
    ]
    statuses: list[DebugModelStatus] = []
    for role, configured_provider, model in configured:
        provider: str = configured_provider or "unconfigured"
        last = next((event for event in reversed(events) if event.role == role), None)
        recorded = actual.get(role)
        if recorded is not None:
            provider, model, status, failure = recorded
            if last is not None and last.model == model:
                status, failure = last.status, last.failure_type
            origin: Literal["analysis", "current_configuration"] = "analysis"
        elif last is not None:
            provider, model, status, failure = (
                last.provider, last.model, last.status, last.failure_type,
            )
            origin = "analysis"
        else:
            status, failure, origin = "not_called", None, "current_configuration"
        if not model:
            continue
        statuses.append(DebugModelStatus(
            role=role, provider=provider, model=model,
            status=status, failure_type=failure, origin=origin,
        ))
    validator_pairs = tuple(dict.fromkeys([*audited_validators, *(
        (event.role, event.provider, event.model) for event in events
        if event.role in {"semantic_validator", "citation_validator"}
    )]))
    if (not validator_pairs and settings.validator_provider and settings.validator_model):
        validator_pairs = (("semantic_validator", settings.validator_provider,
                            settings.validator_model),)
    for role, validator_provider, model in validator_pairs:
        last = next((event for event in reversed(events)
                     if event.role == role and event.provider == validator_provider
                     and event.model == model), None)
        audited = audited_validators.get((role, validator_provider, model))
        if audited is not None and (last is None or last.status == "calling"):
            status, failure = audited
        elif last is not None:
            status, failure = last.status, last.failure_type
        else:
            status, failure = "not_called", None
        statuses.append(DebugModelStatus(
            role=role, provider=validator_provider, model=model, status=status,
            failure_type=failure,
            origin="analysis" if audited is not None or last is not None
            else "current_configuration",
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
            skipped_stages=[
                stage for stage, timestamps in row.stage_timestamps.items()
                if "skipped_at" in timestamps
            ],
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
            ) else LensVerdict.UNABLE_TO_VERIFY_RELIABLY
                if row.status == "failed" and row.failure_code == "normalization_incomplete"
                else None),
            debug_judge_runs=(
                _debug_judge_runs(session, row) if settings.debug_enabled else None
            ),
            debug_diagnostics=(
                _debug_claim_diagnostics(session, row, verdict, model_events(analysis_id))
                if settings.debug_enabled else None
            ),
        ))
    return AnalysisClaimsResponse(analysis_id=analysis_id, claims=summaries)


def _debug_judge_runs(
    session: Session, row: ClaimAnalysisRunRecord,
) -> list[DebugJudgeRun]:
    """Read only allowlisted audit metadata; never expose prompts or responses."""

    verdict = session.get(VerdictRunRecord, row.verdict_run_id) if row.verdict_run_id else None
    raw_qualifications = ((verdict.result_json or {}).get("judge_qualifications")
                          if verdict else None)
    qualifications = ({str(item.get("judge_run_id")): item for item in raw_qualifications
                       if isinstance(item, dict) and item.get("judge_run_id")}
                      if isinstance(raw_qualifications, list) else {})
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
        try:
            validation_result = (JudgeValidationResult.model_validate(validation.result_json)
                                 if validation else None)
        except ValueError:
            validation_result = None
        axes: dict[str, dict[str, str]] = {}
        if validation_result and validation_result.validation_version in {
            "judge-validation-2.3", "judge-validation-2.4", "judge-validation-2.5",
        }:
            from app.validation.joint23 import JointResponse23

            try:
                response = JointResponse23.model_validate_json(json.dumps(
                    (validation_result.relation_validation or {}).get("joint_response")))
                axes = {a.statement_id: {k: str(v) for k, v in a.model_dump().items()
                                         if k in {"direction", "scope", "strength", "role",
                                                  "scope_basis", "finding_basis"}}
                        for a in response.assessments}
            except ValueError:
                pass
        decision = judge.decision_json or {}
        statements = decision.get("statements")
        statement_rows = statements if isinstance(statements, list) else []
        qualification_data = (validation_result.conclusion_qualification
                              if validation_result else None) or {}
        qualification_output = qualification_data.get("output")
        reason_values = (qualification_output.get("reason_codes")
                         if isinstance(qualification_output, dict) else None)
        relation_data = (validation_result.relation_validation
                         if validation_result else None) or {}
        id_values = relation_data.get("id_normalizations")
        unit_id_values = (judge.response_json or {}).get("source_unit_id_normalizations")
        finding_values = relation_data.get("finding_diagnostics")
        failures = (judge.response_json or {}).get("attempt_failures")
        attempt_failure_types = ([str(item.get("category")) for item in failures
                                  if isinstance(item, dict) and item.get("category")]
                                 if isinstance(failures, list) else [])
        verdict_qualification = qualifications.get(str(judge.id), {})
        from app.validation.numeric_effects import NumericFinding

        numeric_summaries: list[DebugNumericFinding] = []
        for raw in (validation_result.numeric_findings or ()) if validation_result else ():
            numeric = NumericFinding.model_validate(raw)
            compact = DebugNumericFinding(
                version=numeric.version, target_id=numeric.target_id, material=numeric.material,
                source_quantity_id=numeric.source_quantity_id,
                source_fidelity=numeric.fidelity.status,
                asserted_values=list(numeric.fidelity.asserted.values),
                source_measure=(numeric.fidelity.source.kind if numeric.fidelity.source else
                                "unknown"),
                claim_measure=numeric.comparability.claim_measure,
                comparability=numeric.comparability.status, numeric_effect=numeric.numeric_effect,
                semantic_scope_checked=numeric.semantic_scope_checked,
                structure_status=numeric.structure_status,
                evidence_ids=list(numeric.fidelity.source_evidence_ids),
                differences=list(numeric.comparability.differences),
                conversions=list(numeric.comparability.conversions),
            )
            if compact not in numeric_summaries:
                numeric_summaries.append(compact)
        exclusion_values = verdict_qualification.get("exclusion_reasons")
        summaries.append(DebugJudgeRun(
            slot=judge.slot, provider=judge.provider, model=judge.model,
            judge_run_id=judge.id,
            validation_run_id=validation.id if validation else None,
            revision_of_judge_run_id=judge.revision_of_judge_run_id,
            semantic_revision_number=judge.semantic_revision_number or 0,
            model_family=judge.model_family, outcome_status=judge.outcome_status,
            error_category=judge.error_category, attempt_count=judge.attempt_count,
            latency_ms=judge.latency_ms,
            validation_status=validation.status if validation else None,
            validation_error_category=validation.error_category if validation else None,
            statement_statuses=({item.statement_id: item.status.value
                                 for item in validation_result.statement_attributions}
                                if validation_result else {}),
            conclusion_status=(validation_result.conclusion_justification.status.value
                               if validation_result and
                               validation_result.conclusion_justification else None),
            targeted_issue_codes=([item.issue_code.value
                                   for item in validation_result.targeted_issues]
                                  if validation_result else []),
            evidence_axes=axes,
            numeric_findings=numeric_summaries,
            proposed_label=(str(decision.get("advisory_label") or decision.get("label"))
                            if decision.get("advisory_label") or decision.get("label") else None),
            validated_evidence_position=(validation_result.validated_evidence_position
                                         if validation_result else None),
            finding_count=len(statement_rows),
            qualification_reason_codes=([str(v) for v in reason_values]
                                        if isinstance(reason_values, list) else []),
            qualification_success=verdict_qualification.get("qualified") is True,
            exclusion_reasons=([str(v) for v in exclusion_values]
                               if isinstance(exclusion_values, list) else []),
            source_ids=({str(s.get("statement_id")): [str(r.get("evidence_id"))
                for r in s.get("evidence_refs", []) if isinstance(r, dict)]
                for s in statement_rows if isinstance(s, dict)}),
            id_normalizations=([dict(v) for v in id_values if isinstance(v, dict)]
                               if isinstance(id_values, list) else []),
            judge_unit_id_normalizations=([
                {str(key): str(value) for key, value in item.items()}
                for item in unit_id_values if isinstance(item, dict)
            ] if isinstance(unit_id_values, list) else []),
            null_diagnostics=({str(k): {str(key): str(value) if value is not None
                else None for key, value in v.items()} for k, v in finding_values.items()
                if isinstance(v, dict)} if isinstance(finding_values, dict) else {}),
            input_tokens=judge.input_tokens, output_tokens=judge.output_tokens,
            model_identity_verified=bool(judge.model_identity_verified),
            model_family_verified=bool(judge.model_family_verified),
            failure_categories=[
                *( ["schema_or_format_retry"] if any(kind in {
                    "schema_violation", "malformed_json", "empty_response",
                    "response_format_unsupported"} for kind in attempt_failure_types) else [] ),
                *( ["source_id_error"] if any(kind in {"invalid_source_unit",
                                                     "invalid_source_quantity"}
                                             for kind in attempt_failure_types)
                    else [] ),
                *( ["source_id_error"] if validation_result and any(
                    item.issue_code == "SOURCE_QUANTITY_REFERENCE_INVALID"
                    for item in validation_result.targeted_issues) else [] ),
                *( ["source_id_error"] if validation and validation.error_category ==
                    "source_id_contract_error" else [] ),
                *( ["unsupported_finding"] if validation_result and any(
                    item.issue_code.value == "STATEMENT_ATTRIBUTION_FAILED"
                    for item in validation_result.targeted_issues) else [] ),
                *( ["optional_numeric_warning"] if validation_result and any(
                    item.issue_code.value.startswith("OPTIONAL_NUMERIC")
                    for item in validation_result.targeted_issues) else [] ),
                *( ["material_numeric_failure"] if validation_result and any(
                    item.issue_code.value in {"NUMERIC_UNCERTAIN", "STATEMENT_NUMERIC_MISMATCH"}
                    for item in validation_result.targeted_issues) else [] ),
                *( ["semantic_axes_unqualified"] if validation_result and
                    validation_result.conclusion_qualification and
                    qualification_output and isinstance(qualification_output, dict) and
                    qualification_output.get("status") != "justified" else [] ),
            ],
            attempt_failure_types=attempt_failure_types,
        ))
    return summaries


def _debug_claim_diagnostics(
    session: Session, row: ClaimAnalysisRunRecord, verdict: VerdictRunRecord | None,
    events: list[dict[str, object]],
) -> dict[str, object]:
    """Allowlisted development snapshot. PASS means pipeline completion only."""
    claim = session.get(Claim, row.claim_id)
    pack_row = (session.get(EvidencePackRecord, row.evidence_pack_id)
                if row.evidence_pack_id else None)
    pack = EvidencePack.model_validate(pack_row.snapshot_json) if pack_row else None
    judges = _debug_judge_runs(session, row)
    selected = set(pack.selected_evidence_ids) if pack else set()
    selected_doc_ids = ({p.passage.document_id for p in pack.passages if p.evidence_id in selected}
                        if pack else set())
    documents = {d.document_id: d for d in pack.documents} if pack else {}
    roles = {role: sum(1 for d in selected_doc_ids if documents[d].evidence_role_hint == role)
             for role in ("direct", "contextual", "incompatible")}
    usable = sum(j.outcome_status == "succeeded" for j in judges)
    attributed = sum(bool(j.statement_statuses) and all(
        status == "supported_by_sources" for status in j.statement_statuses.values())
        for j in judges)
    classified = sum(bool(j.evidence_axes) for j in judges)
    qualified = [j for j in judges if j.qualification_success]
    extraction = bool(claim)
    normalization = bool(claim and claim.outcome and claim.intervention_or_exposure
                         and claim.normalization_status not in {"partial", "pending"})
    run_events = [e for e in events if e.get("claim_id") in {None, str(row.claim_id)}]
    analysis = session.get(AnalysisRunRecord, row.analysis_run_id)
    start = analysis.started_at if analysis and analysis.started_at else row.started_at
    finish = row.finished_at or row.updated_at
    return {
        "extraction": ({"raw_claim": claim.raw_text,
                        "normalized_claim": claim.normalized_text,
                        "claim_type": claim.claim_type, "risk_class": claim.risk_class,
                        "pico": claim.pico_json,
                        "numeric_effect": (claim.pico_json or {}).get("numeric_effect")}
                       if claim else None),
        "retrieval": {"candidates": len(pack.documents) if pack else None,
                      "selected_documents": len(selected_doc_ids) if pack else None,
                      "selected_authoritative": sum(documents[d].source_kind ==
                         "authoritative_public_health" for d in selected_doc_ids),
                      "selected_pubmed": sum(documents[d].source_kind == "pubmed"
                                             for d in selected_doc_ids), "roles": roles},
        "waterfall": {
            "extraction": "PASS" if extraction else "FAIL" if row.status == "failed" else "UNKNOWN",
            "normalization": "PASS" if normalization else "FAIL" if extraction and
                row.status == "failed" else "UNKNOWN",
            "retrieval": "PASS" if pack else "FAIL" if row.status == "failed" and
                row.stage == "retrieving" else "UNKNOWN",
            "selection": "PASS" if selected else "FAIL" if pack else "UNKNOWN",
            "judge_response": f"{usable}/3 usable",
            "source_attribution": f"{attributed}/3",
            "semantic_classification": f"{classified}/3",
            "judge_qualification": f"{len(qualified)}/3",
            "final_aggregation": verdict.verdict if verdict else "UNKNOWN",
        },
        "final": {"qualified_judges": len(qualified),
                  "qualified_positions": [j.validated_evidence_position or j.proposed_label
                                          for j in qualified],
                  "aggregation_reasons": verdict.reason_codes if verdict else [],
                  "production_qualified": verdict.production_qualified if verdict else False,
                  "total_model_calls": (sum(e.get("status") == "calling" for e in run_events)
                                        if run_events else None),
                  "elapsed_ms": (max(0, round((finish - start).total_seconds() * 1000))
                                 if start and finish else None)},
    }


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


@router.get("/{analysis_id}/claims/{claim_id}/report/reading-guide",
            response_model=ReportReadingGuide)
async def get_report_reading_guide(
    analysis_id: UUID, claim_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> ReportReadingGuide:
    """Read named, checked artifacts; use the report's existing release gate."""
    report = await get_claim_report(analysis_id, claim_id, session, settings)
    row = session.get(VerdictRunRecord, report.verdict_run_id)
    try:
        if row is None:
            raise ValueError("Verdict is missing")
        verdict = VerdictResult.model_validate(row.result_json)
        if (verdict.semantic_hash != row.semantic_hash
                or verdict.semantic_hash != semantic_result_hash(verdict)
                or verdict.semantic_hash != report.provenance.verdict_semantic_hash
                or verdict.claim_id != claim_id
                or tuple(verdict.input_judge_run_ids) != tuple(report.provenance.judge_run_ids)
                or tuple(verdict.input_validation_run_ids) != tuple(
                    report.provenance.judge_validation_run_ids)):
            raise ValueError("Verdict provenance mismatch")
        context = load_aggregation_context(session, AggregationInput(
            claim_id=claim_id, evidence_pack_id=verdict.evidence_pack_id,
            evidence_pack_hash=verdict.evidence_pack_hash,
            judge_run_ids=verdict.input_judge_run_ids,
            judge_validation_run_ids=verdict.input_validation_run_ids,
            mode=verdict.mode, policy_version=verdict.policy_version,
        ))
        if context.pack is None or context.claim is None or not context.audit_records_valid:
            raise ValueError("Reading guide source audits unavailable")
        return build_reading_guide(report, verdict, context.pack, context.judges,
                                  context.validations, risk_class=context.claim.risk_class)
    except (ValueError, TypeError, KeyError) as exc:
        raise LensError(503, "report_provenance_invalid",
                        "Source explanation is unavailable.") from exc


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
