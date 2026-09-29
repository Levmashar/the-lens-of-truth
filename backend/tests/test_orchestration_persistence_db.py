"""Optional migrated-PostgreSQL Phase 7A checkpoint and provenance checks."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.claim_extractor import (
    ClaimExtractionPayload,
    ExtractedClaimCandidate,
    PicoCandidate,
)
from app.core.errors import LensError
from app.db.session import SessionLocal
from app.medical.linker import MedicalEntityLinker
from app.medical.mesh import LocalMeshProvider
from app.medical.umls import UnconfiguredUmlsProvider
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
from app.services.analysis_ingestion import AnalysisIngestionService
from app.services.redaction import PiiRedactor
from app.verdict.models import AggregationMode, LensVerdict

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1",
                                reason="Set RUN_DB_TESTS=1 with migrated PostgreSQL")

SOY_SOURCE = "Regular usage of soy increases estrogen levels in body, and lowers muscle gain"


class SoyFixtureExtractor:
    service_name = "offline_soy_fixture"
    model_id = "offline_fixture"

    async def extract(self, *, text: str, language: str) -> ClaimExtractionPayload:
        assert text == SOY_SOURCE
        del language
        return ClaimExtractionPayload(claims=[
            ExtractedClaimCandidate(
                raw_span=text[:54], span_start=0, span_end=54, claim_type="causal",
                pico=PicoCandidate(
                    intervention_or_exposure="Regular usage of soy",
                    outcome="estrogen levels in body",
                ),
            ),
            ExtractedClaimCandidate(
                raw_span=text[60:], span_start=60, span_end=len(text),
                claim_type="causal", coreference_uncertain=True,
                resolved_from_span_start=0, resolved_from_span_end=54,
                pico=PicoCandidate(outcome="muscle gain"),
            ),
        ])


class SoyFixtureIngestion(AnalysisIngestionService):
    async def purge_expired(self, *, session: Session) -> int:
        del session
        return 0


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


def test_exact_soy_sentence_completes_two_claims_with_synthetic_evidence() -> None:
    request = _request(SOY_SOURCE)
    pmids: set[str] = set()
    with SessionLocal() as session:
        run, _ = start_analysis(session, request, idempotency_key=None, retention_hours=1)
        try:
            ingestion = SoyFixtureIngestion(
                storage=Mock(), ocr=Mock(), extractor=SoyFixtureExtractor(),
                redactor=PiiRedactor(), retention_hours=1, maximum_claims=20,
                upload_max_bytes=100, upload_max_pixels=100,
                entity_linker=MedicalEntityLinker(
                    umls=UnconfiguredUmlsProvider(),
                    mesh=LocalMeshProvider({
                        "estrogen": ("D004967", "Estrogens", 0.95),
                        "muscle": ("D009132", "Muscles", 0.95),
                    }),
                ),
            )
            orchestrator = AnalysisOrchestrator(
                ingestion=ingestion, retrieve=fixture_retrieval,
                judge=fixture_judges, validate=fixture_validation,
                mode=AggregationMode.FIXTURE_OR_EVALUATION,
            )

            asyncio.run(orchestrator.run(session, run.id, request))
            session.refresh(run)
            rows = claim_runs(session, run.id)
            assert run.status == "completed"
            assert run.claim_count == run.completed_claims == 2
            assert all(row.report_run_id is not None for row in rows)
            submission = session.get(Submission, run.submission_id)
            assert submission is not None
            assert [claim.normalization_status for claim in submission.claims] == [
                "partially_linked", "partially_linked",
            ]
            assert submission.claims[1].intervention_or_exposure == "Regular usage of soy"
            pmids.update(str(90_000_000 + row.claim_id.int % 9_000_000) for row in rows)
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
