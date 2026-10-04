"""Sequence existing stages; never perform medical reasoning in this layer."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.debug_trace import trace_claim
from app.core.errors import LensError
from app.judging.models import JudgeDecisionV2, JudgeRun
from app.judging.persistence import persist_judge_runs
from app.models.analysis_run import AnalysisRunRecord, ClaimAnalysisRunRecord
from app.models.claim import Claim
from app.models.submission import Submission
from app.pipeline.readiness import ready_for_evidence
from app.report.persistence import build_report_for_verdict, persist_report_run
from app.retrieval.claims import snapshot_claim
from app.retrieval.models import ClaimSnapshot, EvidencePack, RetrievalResult
from app.retrieval.persistence import persist_retrieval
from app.schemas.analysis import CreateAnalysisRequest
from app.validation.models import JudgeValidationRun, ValidationStatus
from app.validation.persistence import persist_validation_run
from app.verdict.models import AggregationInput, AggregationMode
from app.verdict.persistence import load_aggregation_context, persist_verdict_run
from app.verdict.policy import POLICY_V1, POLICY_V3, POLICY_V4
from app.verdict.service import VerdictService

logger = logging.getLogger(__name__)
Retrieve = Callable[[ClaimSnapshot], Awaitable[RetrievalResult]]
Judge = Callable[[UUID, EvidencePack], Awaitable[tuple[JudgeRun, ...]]]
Validate = Callable[[JudgeRun, EvidencePack], Awaitable[JudgeValidationRun]]
Revise = Callable[[JudgeRun, JudgeValidationRun, EvidencePack], Awaitable[JudgeRun]]


class Ingestion(Protocol):
    async def create_analysis(
        self, *, session: Session, request: CreateAnalysisRequest,
        analysis_id: UUID | None = None,
    ) -> Submission: ...


def _checkpoint(
    session: Session, row: AnalysisRunRecord | ClaimAnalysisRunRecord,
    stage: str, *, completed: bool = False,
) -> None:
    row.stage = stage
    row.status = "completed" if completed else "running"
    if row.started_at is None:
        row.started_at = datetime.now(UTC)
    stamps = dict(row.stage_timestamps or {})
    stage_times = dict(stamps.get(stage, {}))
    stage_times.setdefault("started_at", datetime.now(UTC).isoformat())
    if completed:
        stage_times["completed_at"] = datetime.now(UTC).isoformat()
    stamps[stage] = stage_times
    row.stage_timestamps = stamps
    if completed and stage not in row.completed_stages:
        row.completed_stages = [*row.completed_stages, stage]
    row.updated_at = datetime.now(UTC)
    if completed:
        row.finished_at = datetime.now(UTC)
    session.commit()


def _finish_stage(
    session: Session, row: AnalysisRunRecord | ClaimAnalysisRunRecord, stage: str,
) -> None:
    if stage not in row.completed_stages:
        row.completed_stages = [*row.completed_stages, stage]
    stamps = dict(row.stage_timestamps or {})
    stage_times = dict(stamps.get(stage, {}))
    stage_times.setdefault("started_at", datetime.now(UTC).isoformat())
    stage_times["completed_at"] = datetime.now(UTC).isoformat()
    stamps[stage] = stage_times
    row.stage_timestamps = stamps
    row.updated_at = datetime.now(UTC)
    session.commit()


def _skip_stage(
    session: Session, row: AnalysisRunRecord | ClaimAnalysisRunRecord,
    stage: str, *, reason: str,
) -> None:
    """Record an intentional skip without claiming that the stage completed."""

    stamps = dict(row.stage_timestamps or {})
    stamps[stage] = {"skipped_at": datetime.now(UTC).isoformat(), "reason": reason}
    row.stage_timestamps = stamps
    row.updated_at = datetime.now(UTC)
    session.commit()


def _failure_code(exc: Exception, stage: str) -> str:
    if isinstance(exc, LensError):
        return exc.code
    if isinstance(exc, TimeoutError):
        return f"{stage}_timeout"
    return f"{stage}_failed"


@dataclass
class AnalysisOrchestrator:
    ingestion: Ingestion
    retrieve: Retrieve
    judge: Judge
    validate: Validate
    revise: Revise | None = None
    total_timeout_seconds: float = 900.0
    claim_timeout_seconds: float = 300.0
    retrieval_timeout_seconds: float = 180.0
    mode: AggregationMode = AggregationMode.PRODUCTION

    async def run(
        self, session: Session, analysis_id: UUID, request: CreateAnalysisRequest,
    ) -> None:
        """Run one reserved request; never automatically replay a prior run."""

        row = session.get(AnalysisRunRecord, analysis_id)
        if row is None or row.status != "queued":
            raise ValueError("Only a queued analysis run may start")
        try:
            row.started_at = datetime.now(UTC)
            _checkpoint(session, row, "extracting")
            async with asyncio.timeout(self.total_timeout_seconds):
                submission = await self.ingestion.create_analysis(
                    session=session, request=request, analysis_id=analysis_id,
                )
                # Extraction latency never extends the original consent/retention window.
                submission.purge_after = row.purge_after
                row.submission_id = submission.id
                claims = sorted(submission.claims, key=lambda claim: claim.ordinal)
                row.claim_count = len(claims)
                _finish_stage(session, row, "extracting")
                for claim in claims:
                    session.add(ClaimAnalysisRunRecord(
                        id=uuid4(), analysis_run_id=row.id, claim_id=claim.id,
                        ordinal=claim.ordinal, status="queued", stage="queued",
                        completed_stages=[], stage_timestamps={}, judge_run_ids=[],
                        validation_run_ids=[],
                    ))
                session.commit()
                from app.orchestration.state import claim_runs

                for claim_row in claim_runs(session, row.id):
                    try:
                        stored_claim = session.get(Claim, claim_row.claim_id)
                        if stored_claim is None:
                            raise LensError(404, "claim_missing", "Claim is unavailable.")
                        with trace_claim(claim_row.claim_id):
                            async with asyncio.timeout(self.claim_timeout_seconds):
                                await self._run_claim(session, row, claim_row, stored_claim)
                    except Exception as exc:
                        session.rollback()
                        claim_row.status = "failed"
                        claim_row.failure_code = _failure_code(exc, claim_row.stage)
                        claim_row.finished_at = datetime.now(UTC)
                        claim_row.updated_at = datetime.now(UTC)
                        claim_row.stage_timestamps = {
                            **claim_row.stage_timestamps,
                            claim_row.stage: {
                                **claim_row.stage_timestamps.get(claim_row.stage, {}),
                                "failed_at": datetime.now(UTC).isoformat(),
                            },
                        }
                        session.commit()
                        logger.warning(
                            "claim_orchestration_failed analysis=%s ordinal=%d stage=%s "
                            "category=%s", row.id, claim_row.ordinal, claim_row.stage,
                            claim_row.failure_code,
                        )
                    if claim_row.status == "completed":
                        row.completed_claims += 1
                    row.updated_at = datetime.now(UTC)
                    session.commit()
                row.status = ("completed" if row.completed_claims == row.claim_count
                              else "partially_completed" if row.completed_claims
                              else "failed")
                completed = ["normalizing", "retrieving", "judging", "validating",
                             "aggregating", "building_report"]
                rows = claim_runs(session, row.id)
                row.completed_stages = [
                    *row.completed_stages,
                    *(stage for stage in completed if rows and all(
                        stage in item.completed_stages for item in rows
                    ) and stage not in row.completed_stages),
                ]
                row.stage = row.status
                row.finished_at = datetime.now(UTC)
                row.updated_at = datetime.now(UTC)
                session.commit()
        except Exception as exc:
            session.rollback()
            row.status = "partially_completed" if row.completed_claims else "failed"
            row.failure_code = _failure_code(exc, row.stage)
            row.finished_at = datetime.now(UTC)
            row.updated_at = datetime.now(UTC)
            row.stage_timestamps = {**row.stage_timestamps, row.stage: {
                **row.stage_timestamps.get(row.stage, {}),
                "failed_at": datetime.now(UTC).isoformat(),
            }}
            if row.submission_id is not None:
                from app.orchestration.state import claim_runs

                for claim_row in claim_runs(session, row.id):
                    if claim_row.status != "completed" and claim_row.status != "failed":
                        claim_row.status = "failed"
                        claim_row.failure_code = row.failure_code
                        claim_row.finished_at = datetime.now(UTC)
                        claim_row.updated_at = datetime.now(UTC)
            session.commit()
            logger.warning("analysis_orchestration_failed analysis=%s stage=%s category=%s",
                           row.id, row.stage, row.failure_code)

    async def _run_claim(
        self, session: Session, analysis: AnalysisRunRecord,
        row: ClaimAnalysisRunRecord, claim: Claim,
    ) -> None:
        _checkpoint(session, row, "normalizing")
        _checkpoint(session, analysis, "normalizing")
        if not ready_for_evidence(
            claim.normalization_status, pico_json=claim.pico_json,
            quality_json=claim.normalization_quality,
            standalone_status=claim.standalone_status,
            standalone_text=claim.normalized_text,
        ):
            raise LensError(
                422, "normalization_incomplete",
                "The claim lacks a source-grounded exposure or outcome.",
            )
        _finish_stage(session, row, "normalizing")

        _checkpoint(session, row, "retrieving")
        _checkpoint(session, analysis, "retrieving")
        async with asyncio.timeout(self.retrieval_timeout_seconds):
            retrieval = await self.retrieve(snapshot_claim(claim))
        pack_row = persist_retrieval(session, retrieval)
        row.evidence_pack_id = pack_row.id
        row.evidence_pack_hash = pack_row.snapshot_hash
        _finish_stage(session, row, "retrieving")
        pack = retrieval.pack

        if pack.selected_evidence_ids:
            _checkpoint(session, row, "judging")
            _checkpoint(session, analysis, "judging")
            judges = await self.judge(pack_row.id, pack)
        else:
            judges = ()
            _skip_stage(session, row, "judging", reason="no_selected_evidence")
        if judges:
            persist_judge_runs(session, judges)
        row.judge_run_ids = [str(judge.judge_run_id) for judge in judges]
        if pack.selected_evidence_ids:
            _finish_stage(session, row, "judging")

        if pack.selected_evidence_ids:
            _checkpoint(session, row, "validating")
            _checkpoint(session, analysis, "validating")
        else:
            _skip_stage(session, row, "validating", reason="no_selected_evidence")
        validations: list[JudgeValidationRun] = []
        active_judges = list(judges)
        for judge in judges:
            if judge.outcome_status == "succeeded":
                audit = await self.validate(judge, pack)
                persist_validation_run(session, audit)
                validations.append(audit)
                if (self.revise is not None and isinstance(judge.decision, JudgeDecisionV2)
                        and (audit.status in {ValidationStatus.INVALID,
                                              ValidationStatus.PARTIALLY_VALIDATED}
                             or (audit.status == ValidationStatus.UNABLE_TO_VALIDATE
                                 and any(i.issue_code.value == "NUMERIC_UNCERTAIN"
                                         for i in audit.result.targeted_issues)))
                        and audit.result.targeted_issues):
                    try:
                        revised = await self.revise(judge, audit, pack)
                        persist_judge_runs(session, (revised,))
                        active_judges[active_judges.index(judge)] = revised
                        validations.remove(audit)
                        if revised.outcome_status == "succeeded":
                            revised_audit = await self.validate(revised, pack)
                            persist_validation_run(session, revised_audit)
                            validations.append(revised_audit)
                    except Exception:
                        logger.warning(
                            "semantic_revision_unavailable analysis=%s claim=%s judge=%s",
                            analysis.id, claim.id, judge.judge_run_id,
                        )
        row.judge_run_ids = [str(judge.judge_run_id) for judge in active_judges]
        row.validation_run_ids = [str(audit.id) for audit in validations]
        if pack.selected_evidence_ids:
            _finish_stage(session, row, "validating")

        _checkpoint(session, row, "aggregating")
        _checkpoint(session, analysis, "aggregating")
        # Historical synthetic fixture chains still exercise policy 1.1; live
        # V2 judgments use the new contract. No legacy free text is remapped.
        policy = (POLICY_V1 if active_judges and all(
            judge.input_snapshot_version is None for judge in active_judges
        ) else POLICY_V4 if pack.evidence_pack_version == "1.5" else POLICY_V3)
        request = AggregationInput(
            claim_id=claim.id, evidence_pack_id=pack_row.id,
            evidence_pack_hash=pack_row.snapshot_hash,
            judge_run_ids=tuple(judge.judge_run_id for judge in active_judges),
            judge_validation_run_ids=tuple(audit.id for audit in validations),
            mode=self.mode, policy_version=policy.version,
        )
        context = load_aggregation_context(session, request)
        verdict = VerdictService(policy=policy).aggregate(request, context)
        verdict_row = persist_verdict_run(session, verdict)
        row.verdict_run_id = verdict_row.id
        _finish_stage(session, row, "aggregating")

        _checkpoint(session, row, "building_report")
        _checkpoint(session, analysis, "building_report")
        report = build_report_for_verdict(session, verdict_row.id)
        report_row = persist_report_run(session, report)
        row.report_run_id = report_row.id
        _checkpoint(session, row, "building_report", completed=True)
