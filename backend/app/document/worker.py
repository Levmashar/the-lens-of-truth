"""Document lifecycle; frozen audits and task-local sessions at every checkpoint."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import SecretStr, ValidationError

from app.adapters.pmc import PmcFullTextAdapter
from app.core.config import Settings
from app.db.session import SessionLocal
from app.dependencies import (
    build_entity_linker,
    get_authoritative_adapter,
    get_crossref_adapter,
    get_pubmed_adapter,
)
from app.document.evaluation import evaluate_group
from app.document.models import DocumentPlan
from app.document.persistence import insert_document_artifact
from app.document.report import build_document_report
from app.document.retrieval import DocumentSourceCache, retrieve_document_group
from app.models.analysis_run import AnalysisRunRecord
from app.schemas.analysis import CreateAnalysisRequest
from app.services.analysis_ingestion import AnalysisIngestionService

logger = logging.getLogger(__name__)


def exception_diagnostic(exc: Exception, settings: Settings) -> dict[str, Any]:
    """Bounded development audit details without inputs or credential values."""
    message = str(exc) if not isinstance(exc, ValidationError) else "Invalid frozen contract"
    for value in vars(settings).values():
        if isinstance(value, SecretStr) and value.get_secret_value():
            message = message.replace(value.get_secret_value(), "[REDACTED]")
    diagnostic: dict[str, Any] = {"exception_type": type(exc).__name__, "message": message[:500]}
    if isinstance(exc, ValidationError):
        diagnostic["issues"] = [
            {"loc": list(error["loc"]), "type": error["type"], "message": error["msg"][:250]}
            for error in exc.errors(include_input=False, include_context=False)[:8]
        ]
    return diagnostic


def checkpoint(
    analysis_id: UUID,
    stage: str,
    *,
    completed: bool = False,
    claim_count: int | None = None,
    completed_claims: int | None = None,
    status: str = "running",
    failure: str | None = None,
) -> None:
    with SessionLocal() as session:
        row = session.get(AnalysisRunRecord, analysis_id)
        if row is None:
            raise ValueError("Document analysis has expired")
        now = datetime.now(UTC)
        row.status, row.stage = status, stage
        row.started_at = row.started_at or now
        stamps = {**row.stage_timestamps}
        stamps["document"] = {"mode": "document", "version": "document-workflow-1.0"}
        stamps[stage] = {
            **stamps.get(stage, {}),
            "completed_at" if completed else "started_at": now.isoformat(),
        }
        row.stage_timestamps = stamps
        if completed and stage not in row.completed_stages:
            row.completed_stages = [*row.completed_stages, stage]
        if claim_count is not None:
            row.claim_count = claim_count
        if completed_claims is not None:
            row.completed_claims = completed_claims
        if status in {"completed", "partially_completed", "failed"}:
            row.finished_at = now
        row.failure_code = failure
        row.updated_at = now
        session.commit()


def persist(
    analysis_id: UUID,
    kind: Any,
    snapshot: dict[str, Any],
    group_id: str | None = None,
    slot: int | None = None,
) -> None:
    # Never hand a SQLAlchemy session to concurrent model tasks.
    with SessionLocal() as session:
        insert_document_artifact(session, analysis_id, kind, snapshot, group_id, slot)


async def run_document(
    analysis_id: UUID,
    request: CreateAnalysisRequest,
    settings: Settings,
    ingestion: AnalysisIngestionService,
) -> None:
    checkpoint(analysis_id, "extracting")
    plan: DocumentPlan | None = None
    evidence: dict[str, dict[str, Any]] = {}
    runs: dict[str, list[dict[str, Any]]] = {}
    failures: dict[str, str] = {}
    try:
        async with asyncio.timeout(settings.analysis_total_timeout_seconds):
            with SessionLocal() as session:
                row = session.get(AnalysisRunRecord, analysis_id)
                assert row is not None
                submission, text = await ingestion.prepare_document_submission(
                    session=session,
                    request=request,
                    analysis_id=analysis_id,
                    purge_after=row.purge_after,
                )
                row.submission_id = submission.id
                session.commit()
            from app.document.planner import plan_document

            plan = await plan_document(text, settings)
            persist(analysis_id, "plan", plan.model_dump(mode="json"))
            checkpoint(analysis_id, "extracting", completed=True, claim_count=len(plan.assertions))
            checkpoint(analysis_id, "normalizing", completed=True)
            adapter = get_pubmed_adapter(settings)
            fulltext = PmcFullTextAdapter(adapter)
            source_cache = DocumentSourceCache()
            linker = build_entity_linker(settings)

            def save_report(status: str = "running") -> dict[str, Any]:
                assert plan is not None
                report = build_document_report(
                    analysis_id,
                    plan,
                    evidence,
                    runs,
                    app_env=settings.app_env,
                    status=status,
                    failures=failures,
                )
                persist(analysis_id, "report", report)
                return report

            save_report()
            # Bounded groups share per-analysis public-source cache. Within each
            # group every judge→checker chain runs independently and concurrently.
            for group in plan.groups:
                try:
                    if not any(
                        plan.assertion(aid).checkable
                        and plan.assertion(aid).planning_status == "ready"
                        for aid in group.assertion_ids
                    ):
                        continue
                    checkpoint(analysis_id, "retrieving")
                    async with asyncio.timeout(settings.analysis_retrieval_timeout_seconds):
                        snapshot = await retrieve_document_group(
                            analysis_id,
                            plan,
                            group,
                            adapter,
                            crossref=get_crossref_adapter(settings),
                            authoritative=get_authoritative_adapter(settings),
                            fulltext=fulltext,
                            linker=linker,
                            source_cache=source_cache,
                        )
                    evidence[group.group_id] = snapshot.model_dump(mode="json")
                    persist(analysis_id, "group_evidence", evidence[group.group_id], group.group_id)
                    checkpoint(analysis_id, "retrieving", completed=True)
                    checkpoint(analysis_id, "judging")
                    save_report()

                    async def on_result(
                        result: dict[str, Any],
                        group_id: str = group.group_id,
                        evidence_hash: str = snapshot.snapshot_hash,
                    ) -> None:
                        runs.setdefault(group_id, []).append(result)
                        persist(
                            analysis_id,
                            "group_judge",
                            {
                                "version": "document-judge-audit-1.0",
                                "document_sha256": plan.original_sha256,
                                "group_evidence_hash": evidence_hash,
                                **result,
                            },
                            group_id,
                            result["slot"],
                        )
                        report = save_report()
                        checkpoint(
                            analysis_id,
                            "validating",
                            completed_claims=report["progress"]["assertions_completed"],
                        )

                    await evaluate_group(
                        plan,
                        group,
                        snapshot.pack,
                        snapshot.source_match.model_dump(mode="json"),
                        analysis_id,
                        settings,
                        on_result=on_result,
                        claim_snapshots=snapshot.claim_snapshots,
                        per_assertion_evidence_ids=snapshot.per_assertion_evidence_ids,
                        normalization_ready=snapshot.normalization_ready,
                    )
                    checkpoint(analysis_id, "judging", completed=True)
                    checkpoint(analysis_id, "validating", completed=True)
                except Exception as exc:
                    failures[group.group_id] = type(exc).__name__
                    persist(
                        analysis_id,
                        "error",
                        {
                            "version": "document-error-1.0",
                            "group_id": group.group_id,
                            "failure": type(exc).__name__,
                            "diagnostic": exception_diagnostic(exc, settings),
                        },
                        group.group_id,
                    )
                    logger.warning(
                        "document_group_failed analysis=%s group=%s category=%s",
                        analysis_id,
                        group.group_id,
                        type(exc).__name__,
                    )
                    save_report()
            checkpoint(analysis_id, "aggregating", completed=True)
            checkpoint(analysis_id, "building_report")
            report = save_report()
            available = [
                a for g in report["groups"] for a in g["assertions"] if a["status"] == "completed"
            ]
            unavailable = [
                a
                for g in report["groups"]
                for a in g["assertions"]
                if a["status"] in {"unavailable", "pending"}
            ]
            status = (
                "partially_completed"
                if unavailable and available
                else "failed"
                if unavailable
                else "completed"
            )
            save_report(status)
            checkpoint(
                analysis_id,
                "building_report",
                completed=True,
                status=status,
                completed_claims=len(available),
                failure="document_assessments_unavailable" if status == "failed" else None,
            )
    except Exception as exc:
        if plan is not None:
            for group in plan.groups:
                failures[group.group_id] = type(exc).__name__
                persist(
                    analysis_id,
                    "error",
                    {
                        "version": "document-error-1.0",
                        "failure": type(exc).__name__,
                        "diagnostic": exception_diagnostic(exc, settings),
                        "group_id": group.group_id,
                    },
                    group.group_id,
                )
            save_report("failed")
        with SessionLocal() as session:
            current = session.get(AnalysisRunRecord, analysis_id)
            failed_stage = current.stage if current is not None else "extracting"
        checkpoint(
            analysis_id,
            failed_stage,
            status="failed",
            failure=getattr(exc, "code", "document_workflow_unavailable"),
        )
        persist(
            analysis_id,
            "error",
            {
                "version": "document-error-1.0",
                "failure": type(exc).__name__,
                "diagnostic": exception_diagnostic(exc, settings),
            },
        )
        logger.warning(
            "document_workflow_failed analysis=%s category=%s", analysis_id, type(exc).__name__
        )
