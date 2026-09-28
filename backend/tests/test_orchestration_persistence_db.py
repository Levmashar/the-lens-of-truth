"""Optional migrated-PostgreSQL Phase 7A checkpoint and provenance checks."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.errors import LensError
from app.db.session import SessionLocal
from app.models.analysis_run import AnalysisRunRecord, ClaimAnalysisRunRecord
from app.models.evidence import EvidenceDocument
from app.models.report_run import ReportRunRecord
from app.models.submission import Submission
from app.orchestration.service import AnalysisOrchestrator
from app.orchestration.smoke import (
    FIXTURE_TEXT,
    FixtureIngestion,
    fixture_judges,
    fixture_retrieval,
    fixture_validation,
)
from app.orchestration.state import claim_runs, start_analysis
from app.report.models import LensReport
from app.schemas.analysis import AnalysisInput, Consent, CreateAnalysisRequest
from app.verdict.models import AggregationMode, LensVerdict

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1",
                                reason="Set RUN_DB_TESTS=1 with migrated PostgreSQL")


def _request(text: str) -> CreateAnalysisRequest:
    return CreateAnalysisRequest(
        input=AnalysisInput(type="text", text=text),
        consent=Consent(privacy_notice_version="fixture", accepted=True),
    )


def _cleanup(session: object, run_id: UUID, pmids: set[str]) -> None:
    run = session.get(AnalysisRunRecord, run_id)
    if run is not None:
        if run.submission_id:
            submission = session.get(Submission, run.submission_id)
            if submission is not None:
                session.delete(submission)
        else:
            session.delete(run)
        session.commit()
    for pmid in pmids:
        for document in session.scalars(select(EvidenceDocument).where(
            EvidenceDocument.pmid == pmid,
            EvidenceDocument.canonical_url == "https://example.invalid/synthetic-evidence",
        )):
            session.delete(document)
    session.commit()


def test_postgres_full_chain_and_idempotent_start() -> None:
    request = _request(FIXTURE_TEXT)
    key = f"fixture-{uuid4()}"
    pmids: set[str] = set()
    with SessionLocal() as session:
        run, created = start_analysis(session, request, idempotency_key=key,
                                      retention_hours=1)
        try:
            assert created
            repeated, created = start_analysis(session, request, idempotency_key=key,
                                               retention_hours=1)
            assert not created and repeated.id == run.id
            with pytest.raises(LensError) as conflict:
                start_analysis(session, _request("Treatment Z reduces Q in adults."),
                               idempotency_key=key, retention_hours=1)
            assert conflict.value.status_code == 409
            orchestrator = AnalysisOrchestrator(
                ingestion=FixtureIngestion((FIXTURE_TEXT,)), retrieve=fixture_retrieval,
                judge=fixture_judges, validate=fixture_validation,
                mode=AggregationMode.FIXTURE_OR_EVALUATION,
            )
            asyncio.run(orchestrator.run(session, run.id, request))
            session.refresh(run)
            row = claim_runs(session, run.id)[0]
            assert run.status == row.status == "completed"
            assert row.evidence_pack_id and row.evidence_pack_hash
            assert len(row.judge_run_ids) == len(row.validation_run_ids) == 3
            assert row.verdict_run_id and row.report_run_id
            stored = session.get(ReportRunRecord, row.report_run_id)
            assert stored is not None
            report = LensReport.model_validate(stored.result_json)
            assert report.verdict == LensVerdict.SUPPORTED
            assert report.production_qualified is False
            assert report.provenance.evidence_pack_id == row.evidence_pack_id
            assert set(report.provenance.judge_run_ids) == set(map(UUID, row.judge_run_ids))
            assert set(report.provenance.judge_validation_run_ids) == set(
                map(UUID, row.validation_run_ids)
            )
            assert report.provenance.verdict_run_id == row.verdict_run_id
            assert report.key_evidence[0].source_url == (
                "https://example.invalid/synthetic-evidence"
            )
            pmids.update(source.pmid for source in report.sources)
            with pytest.raises(ValueError, match="queued"):
                asyncio.run(orchestrator.run(session, run.id, request))
            assert session.get(ClaimAnalysisRunRecord, row.id) is not None
        finally:
            session.rollback()
            _cleanup(session, run.id, pmids)


def test_postgres_multiclaim_failure_isolation() -> None:
    claims = (FIXTURE_TEXT, "Treatment Z reduces Q in adults.",
              "Treatment A reduces B in adults.")
    request = _request(" ".join(claims))
    pmids: set[str] = set()
    with SessionLocal() as session:
        run, _ = start_analysis(session, request, idempotency_key=None, retention_hours=1)
        try:
            async def retrieve(snapshot: object) -> object:
                if snapshot.raw_text == claims[1]:
                    raise RuntimeError("secret upstream failure")
                return await fixture_retrieval(snapshot)

            orchestrator = AnalysisOrchestrator(
                ingestion=FixtureIngestion(claims), retrieve=retrieve,
                judge=fixture_judges, validate=fixture_validation,
                mode=AggregationMode.FIXTURE_OR_EVALUATION,
            )
            asyncio.run(orchestrator.run(session, run.id, request))
            session.refresh(run)
            rows = claim_runs(session, run.id)
            assert run.status == "partially_completed"
            assert run.claim_count == 3 and run.completed_claims == 2
            assert [row.status for row in rows] == ["completed", "failed", "completed"]
            assert rows[1].failure_code == "retrieving_failed"
            assert rows[1].evidence_pack_id is None
            assert rows[0].evidence_pack_id != rows[2].evidence_pack_id
            assert rows[0].report_run_id != rows[2].report_run_id
            for row in (rows[0], rows[2]):
                stored = session.get(ReportRunRecord, row.report_run_id)
                assert stored is not None
                report = LensReport.model_validate(stored.result_json)
                pmids.update(source.pmid for source in report.sources)
        finally:
            session.rollback()
            _cleanup(session, run.id, pmids)


def test_expired_idempotency_key_cannot_resurrect_run() -> None:
    request = _request(FIXTURE_TEXT)
    key = f"expired-fixture-{uuid4()}"
    with SessionLocal() as session:
        run, _ = start_analysis(session, request, idempotency_key=key, retention_hours=1)
        try:
            run.purge_after = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()
            with pytest.raises(LensError) as expired:
                start_analysis(session, request, idempotency_key=key, retention_hours=1)
            assert expired.value.status_code == 410
            assert expired.value.code == "idempotency_key_expired"
        finally:
            session.rollback()
            _cleanup(session, run.id, set())
