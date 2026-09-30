"""Single-process background composition; no new broker or provider bypass."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from app.adapters.entailment import OpenAICompatibleEntailmentValidator
from app.adapters.judge import OpenAICompatibleJudgeProvider
from app.adapters.ocr import TesseractOcrAdapter
from app.adapters.storage import LocalFilesystemUploadStorage
from app.core.config import Settings
from app.core.debug_trace import trace_analysis
from app.db.session import SessionLocal
from app.dependencies import (
    build_analysis_ingestion_service,
    get_claim_extractor,
    get_crossref_adapter,
    get_pubmed_adapter,
)
from app.judging.config import configured_slots, is_search_enabled_model
from app.judging.models import JudgeRun
from app.judging.service import JudgeService
from app.models.analysis_run import AnalysisRunRecord
from app.orchestration.service import AnalysisOrchestrator
from app.retrieval.models import ClaimSnapshot, EvidencePack, RetrievalResult
from app.retrieval.service import retrieve_pubmed
from app.schemas.analysis import CreateAnalysisRequest
from app.validation.models import JudgeValidationRun
from app.validation.service import ValidationService
from app.verdict.models import AggregationMode

logger = logging.getLogger(__name__)


def development_entailment_validator(
    settings: Settings, judge: JudgeRun,
) -> OpenAICompatibleEntailmentValidator | None:
    """Cross-check with another configured family only in evaluation runs.

    This is a live *unapproved* semantic check, not production certification.
    Search-enabled gateway modes are not used as validators.
    """

    if settings.app_env not in {"development", "test"}:
        return None
    try:
        candidates = configured_slots(settings)
    except ValueError:
        return None
    for slot in reversed(candidates):
        if (slot.model_family.casefold() != judge.model_family.casefold()
                and not is_search_enabled_model(slot.model)):
            return OpenAICompatibleEntailmentValidator(
                provider=slot.provider, model=slot.model,
                base_url=slot.base_url, api_key=slot.api_key,
            )
    return None


def build_orchestrator(settings: Settings) -> AnalysisOrchestrator:
    """Build adapters inside the worker, never during the fast HTTP acknowledgement."""

    ingestion = build_analysis_ingestion_service(
        settings=settings,
        storage=LocalFilesystemUploadStorage(root=settings.upload_storage_path),
        ocr=TesseractOcrAdapter(
            executable=settings.ocr_executable, timeout_seconds=settings.ocr_timeout_seconds,
        ),
        extractor=get_claim_extractor(settings),
    )

    async def retrieval(claim: ClaimSnapshot) -> RetrievalResult:
        return await retrieve_pubmed(
            claim, get_pubmed_adapter(settings),
            selected_limit=settings.pubmed_selected_evidence_limit,
            max_per_document=settings.pubmed_max_passages_per_document,
            crossref=get_crossref_adapter(settings),
            crossref_total_timeout_seconds=settings.crossref_total_timeout_seconds,
        )

    provider = OpenAICompatibleJudgeProvider(settings.judge_attempt_timeout_seconds)
    judge_service = JudgeService(
        providers={"miri": provider, "openai_compatible": provider},
        attempt_timeout_seconds=settings.judge_attempt_timeout_seconds,
        total_timeout_seconds=settings.judge_total_timeout_seconds,
        concurrency_limit=settings.judge_concurrency_limit,
    )

    async def judging(pack_id: UUID, pack: EvidencePack) -> tuple[JudgeRun, ...]:
        try:
            slots = configured_slots(settings)
        except ValueError:
            logger.warning("judge_configuration_rejected")
            return ()
        if not slots:
            return ()
        runs, _ = await judge_service.run(
            pack_id, pack, slots,
            allow_same_family=(settings.app_env in {"development", "test"}
                               and settings.judge_allow_same_family_development),
            app_env=settings.app_env,
            allow_search_enabled_development=settings.judge_allow_search_enabled_development,
        )
        return runs

    async def revision(
        judge: JudgeRun, audit: JudgeValidationRun, pack: EvidencePack,
    ) -> JudgeRun:
        slots = configured_slots(settings)
        slot = next((item for item in slots if item.slot == judge.slot), None)
        if slot is None:
            raise ValueError("Original judge slot is no longer configured")
        return await judge_service.revise(judge, audit, pack, slot)

    async def validation(judge: JudgeRun, pack: EvidencePack) -> JudgeValidationRun:
        validator = development_entailment_validator(settings, judge)
        return await ValidationService(
            entailment_validator=validator, semantic_validator=validator,
        ).run(judge, pack)

    return AnalysisOrchestrator(
        ingestion=ingestion, retrieve=retrieval, judge=judging, validate=validation,
        revise=revision,
        total_timeout_seconds=settings.analysis_total_timeout_seconds,
        claim_timeout_seconds=settings.analysis_claim_timeout_seconds,
        retrieval_timeout_seconds=settings.analysis_retrieval_timeout_seconds,
        mode=(AggregationMode.FIXTURE_OR_EVALUATION
              if settings.app_env in {"development", "test"}
              else AggregationMode.PRODUCTION),
    )


async def run_background(
    analysis_id: UUID, request: CreateAnalysisRequest, settings: Settings,
) -> None:
    """Use a fresh session after the HTTP dependency scope has closed."""

    with trace_analysis(analysis_id, enabled=settings.debug_enabled):
        await _run_background_traced(analysis_id, request, settings)


async def _run_background_traced(
    analysis_id: UUID, request: CreateAnalysisRequest, settings: Settings,
) -> None:
    """Execute all provider calls within the optional trace context."""

    with SessionLocal() as session:
        try:
            orchestrator = build_orchestrator(settings)
        except Exception:
            # Adapter composition can fail before run() starts. Leave a safe
            # terminal checkpoint instead of an indefinitely queued request.
            session.rollback()
            row = session.get(AnalysisRunRecord, analysis_id)
            if row is not None and row.status == "queued":
                now = datetime.now(UTC)
                row.status = "failed"
                row.failure_code = "worker_initialization_failed"
                row.finished_at = now
                row.updated_at = now
                row.stage_timestamps = {**row.stage_timestamps, "queued": {
                    **row.stage_timestamps.get("queued", {}),
                    "failed_at": now.isoformat(),
                }}
                session.commit()
            logger.warning("analysis_worker_initialization_failed analysis=%s", analysis_id)
            return
        await orchestrator.run(session, analysis_id, request)
