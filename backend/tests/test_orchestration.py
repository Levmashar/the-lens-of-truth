"""Offline full-chain orchestration tests with synthetic, non-medical fixtures."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.api.routes.analyses import get_analysis_claims, get_claim_report
from app.core.config import Settings
from app.core.errors import LensError
from app.judging.models import JudgeLabel
from app.models.analysis_run import AnalysisRunRecord, ClaimAnalysisRunRecord
from app.models.claim import Claim
from app.models.report_run import ReportRunRecord
from app.models.retrieval import EvidencePackRecord
from app.models.submission import Submission
from app.models.verdict_run import VerdictRunRecord
from app.orchestration.service import AnalysisOrchestrator
from app.orchestration.smoke import (
    FIXTURE_TEXT,
    FixtureIngestion,
    fixture_judges,
    fixture_retrieval,
    fixture_validation,
)
from app.orchestration.state import get_run, mark_interrupted
from app.orchestration.worker import run_background
from app.pipeline.readiness import ready_for_evidence
from app.report.builder import build_report
from app.report.models import LensReport
from app.schemas.analysis import AnalysisInput, Consent, CreateAnalysisRequest
from app.validation.models import ValidationStatus
from app.verdict.models import AggregationContext, AggregationMode, ClaimFacts, LensVerdict


class MemorySession:
    def __init__(self) -> None:
        self.rows: dict[tuple[type, object], object] = {}

    def add(self, row: object) -> None:
        self.rows[type(row), row.id] = row
        if isinstance(row, Submission):
            for claim in row.claims:
                self.rows[Claim, claim.id] = claim

    def get(self, kind: type, key: object) -> object | None:
        return self.rows.get((kind, key))

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def refresh(self, _row: object) -> None:
        return None


def request_for(text: str) -> CreateAnalysisRequest:
    return CreateAnalysisRequest(
        input=AnalysisInput(type="text", text=text),
        consent=Consent(privacy_notice_version="fixture", accepted=True),
    )


async def run_fixture(
    monkeypatch: pytest.MonkeyPatch, claims: tuple[str, ...], *,
    unavailable: bool = False, failed_ordinal: int | None = None,
    no_results: bool = False, contradicted: bool = False,
    one_failed_judge: bool = False, unvalidated: bool = False,
    corrupt_pack: bool = False, extraction_failure: bool = False,
    normalization_status: str = "normalized",
) -> tuple[MemorySession, AnalysisRunRecord, dict[str, object]]:
    session = MemorySession()
    text = " ".join(claims)
    request = request_for(text)
    run = AnalysisRunRecord(
        id=uuid4(), status="queued", stage="queued", completed_stages=[],
        claim_count=0, completed_claims=0, request_hash=hashlib.sha256(text.encode()).hexdigest(),
        purge_after=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(run)
    artifacts: dict[str, object] = {"packs": {}, "judges": {}, "validations": {},
                                    "verdicts": {}, "reports": {}}

    def claim_rows(_session: object, analysis_id: object) -> list[ClaimAnalysisRunRecord]:
        return sorted((row for (kind, _), row in session.rows.items()
                       if kind is ClaimAnalysisRunRecord and row.analysis_run_id == analysis_id),
                      key=lambda row: row.ordinal)

    def persist_pack(_session: object, result: object) -> object:
        pack = result.pack
        artifacts["packs"][pack.claim_id] = pack
        row = EvidencePackRecord(
            id=uuid4(), claim_id=pack.claim_id, run_id=uuid4(),
            version=pack.evidence_pack_version, snapshot_hash=pack.snapshot_hash,
            snapshot_json=pack.model_dump(mode="json"), created_at=datetime.now(UTC),
        )
        session.add(row)
        return row

    def persist_judges(_session: object, runs: object) -> None:
        for judge in runs:
            artifacts["judges"][judge.judge_run_id] = judge

    def persist_validation(_session: object, audit: object) -> None:
        artifacts["validations"][audit.id] = audit

    def context(_session: object, aggregation: object) -> AggregationContext:
        pack = artifacts["packs"][aggregation.claim_id]
        claim = session.get(Claim, aggregation.claim_id)
        return AggregationContext(
            claim=ClaimFacts(claim_id=claim.id, normalization_status=claim.normalization_status,
                             risk_class=claim.risk_class,
                             normalization_reviewed=ready_for_evidence(
                                 claim.normalization_status, pico_json=claim.pico_json,
                                 quality_json=claim.normalization_quality,
                             )),
            pack=pack, stored_pack_hash=pack.snapshot_hash,
            retrieval_status="ok",
            judges=tuple(artifacts["judges"][item] for item in aggregation.judge_run_ids),
            validations=tuple(artifacts["validations"][item]
                              for item in aggregation.judge_validation_run_ids),
        )

    def persist_verdict(_session: object, result: object) -> object:
        row_id = uuid4()
        artifacts["verdicts"][row_id] = result
        row = VerdictRunRecord(
            id=row_id, claim_id=result.claim_id,
            evidence_pack_id=result.evidence_pack_id,
            semantic_hash=result.semantic_hash,
            verdict=result.verdict.value,
            production_qualified=result.production_qualified,
        )
        session.add(row)
        return row

    def build_report_for(_session: object, verdict_id: object) -> LensReport:
        verdict = artifacts["verdicts"][verdict_id]
        pack = artifacts["packs"][verdict.claim_id]
        return build_report(
            verdict_id, verdict, pack,
            tuple(artifacts["judges"][item] for item in verdict.input_judge_run_ids),
            tuple(artifacts["validations"][item]
                  for item in verdict.input_validation_run_ids),
        )

    def persist_report(_session: object, report: LensReport) -> object:
        row = ReportRunRecord(
            id=uuid4(), verdict_run_id=report.verdict_run_id,
            report_version=report.report_version,
            report_builder_version=report.provenance.report_builder_version,
            result_json=report.model_dump(mode="json"),
            semantic_hash=report.semantic_hash,
            production_qualified=report.production_qualified,
        )
        session.add(row)
        artifacts["reports"][row.id] = report
        return row

    monkeypatch.setattr("app.orchestration.state.claim_runs", claim_rows)
    monkeypatch.setattr("app.api.routes.analyses.claim_runs", claim_rows)
    monkeypatch.setattr("app.orchestration.service.persist_retrieval", persist_pack)
    monkeypatch.setattr("app.orchestration.service.persist_judge_runs", persist_judges)
    monkeypatch.setattr("app.orchestration.service.persist_validation_run", persist_validation)
    monkeypatch.setattr("app.orchestration.service.load_aggregation_context", context)
    monkeypatch.setattr("app.orchestration.service.persist_verdict_run", persist_verdict)
    monkeypatch.setattr("app.orchestration.service.build_report_for_verdict", build_report_for)
    monkeypatch.setattr("app.orchestration.service.persist_report_run", persist_report)

    async def retrieve(claim: object) -> object:
        stored = session.get(Claim, claim.claim_id)
        if failed_ordinal == stored.ordinal:
            raise RuntimeError("upstream-secret-body")
        result = await fixture_retrieval(claim, no_results=no_results,
                                         contradicted=contradicted)
        if corrupt_pack:
            bad = result.pack.model_copy(update={"snapshot_hash": "0" * 64})
            return result.model_copy(update={"pack": bad})
        return result

    async def judges(pack_id: object, pack: object) -> object:
        runs = await fixture_judges(
            pack_id, pack, unavailable=unavailable,
            label=JudgeLabel.CONTRADICTED if contradicted else JudgeLabel.SUPPORTED,
        )
        if one_failed_judge:
            failed = runs[-1].model_copy(update={
                "decision": None, "response_json": None,
                "outcome_status": "failed", "error_category": "timeout",
            })
            return (*runs[:-1], failed)
        return runs

    async def validation(judge: object, pack: object) -> object:
        audit = await fixture_validation(judge, pack)
        if unvalidated:
            return audit.model_copy(update={
                "status": ValidationStatus.UNABLE_TO_VALIDATE,
                "result": audit.result.model_copy(update={
                    "validation_status": ValidationStatus.UNABLE_TO_VALIDATE,
                }),
            })
        return audit

    class FailingIngestion(FixtureIngestion):
        async def create_analysis(self, **_: object) -> object:
            raise RuntimeError("sensitive-extractor-body")

    class StatusIngestion(FixtureIngestion):
        async def create_analysis(
            self, *, session: Session, request: CreateAnalysisRequest,
            analysis_id: UUID | None = None,
        ) -> Submission:
            submission = await super().create_analysis(
                session=session, request=request, analysis_id=analysis_id,
            )
            for claim in submission.claims:
                claim.normalization_status = normalization_status
                if normalization_status == "partially_linked":
                    claim.normalization_quality = {
                        "required_slots_missing": [], "missing_explicit_concepts": [],
                        "normalization_warnings": [], "normalization_coverage": 1.0,
                    }
            return submission

    orchestrator = AnalysisOrchestrator(
        ingestion=FailingIngestion(claims) if extraction_failure else StatusIngestion(claims),
        retrieve=retrieve, judge=judges, validate=validation,
        mode=AggregationMode.FIXTURE_OR_EVALUATION,
    )
    await orchestrator.run(session, run.id, request)
    return session, run, artifacts


def test_supported_full_chain_has_explicit_artifact_relationships(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, run, artifacts = asyncio.run(run_fixture(monkeypatch, (FIXTURE_TEXT,)))
    rows = [row for (kind, _), row in session.rows.items() if kind is ClaimAnalysisRunRecord]
    row = rows[0]
    report = artifacts["reports"][row.report_run_id]
    verdict = artifacts["verdicts"][row.verdict_run_id]
    assert run.status == row.status == "completed"
    assert run.claim_count == run.completed_claims == 1
    assert len(row.judge_run_ids) == len(row.validation_run_ids) == 3
    assert verdict.verdict == report.verdict == LensVerdict.SUPPORTED
    assert report.production_qualified is False
    assert report.verification_status.development_notice
    assert report.provenance.evidence_pack_id == row.evidence_pack_id
    assert report.provenance.evidence_pack_hash == row.evidence_pack_hash
    assert set(report.provenance.judge_run_ids) == set(map(UUID, row.judge_run_ids))
    assert set(report.provenance.judge_validation_run_ids) == set(
        map(UUID, row.validation_run_ids)
    )
    assert report.provenance.verdict_run_id == row.verdict_run_id
    assert report.key_evidence[0].exact_excerpt.startswith("In adults, Treatment X")


def test_unavailable_judges_become_unable_not_not_enough_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, run, artifacts = asyncio.run(run_fixture(monkeypatch, (FIXTURE_TEXT,),
                                                      unavailable=True))
    row = next(row for (kind, _), row in session.rows.items()
               if kind is ClaimAnalysisRunRecord)
    report = artifacts["reports"][row.report_run_id]
    assert run.status == "completed"
    assert row.judge_run_ids == row.validation_run_ids == []
    assert report.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert not report.key_evidence


def test_partially_linked_claim_continues_but_missing_pico_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, linked_run, _ = asyncio.run(run_fixture(
        monkeypatch, (FIXTURE_TEXT,), normalization_status="partially_linked",
    ))
    incomplete_session, incomplete_run, _ = asyncio.run(run_fixture(
        monkeypatch, (FIXTURE_TEXT,), normalization_status="partial",
    ))

    assert linked_run.status == "completed" and linked_run.completed_claims == 1
    assert incomplete_run.status == "failed" and incomplete_run.completed_claims == 0
    failed_row = next(row for (kind, _), row in incomplete_session.rows.items()
                      if kind is ClaimAnalysisRunRecord)
    assert failed_row.failure_code == "normalization_incomplete"


def test_multiclaim_isolation_and_partial_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims = (FIXTURE_TEXT, "Treatment Z reduces Q in adults.",
              "Treatment A reduces B in adults.")
    session, run, artifacts = asyncio.run(run_fixture(monkeypatch, claims, failed_ordinal=2))
    rows = sorted((row for (kind, _), row in session.rows.items()
                   if kind is ClaimAnalysisRunRecord), key=lambda row: row.ordinal)
    assert run.status == "partially_completed"
    assert run.claim_count == 3 and run.completed_claims == 2
    assert [row.status for row in rows] == ["completed", "failed", "completed"]
    assert rows[1].failure_code == "retrieving_failed"
    assert len({rows[0].evidence_pack_id, rows[2].evidence_pack_id}) == 2
    assert rows[0].verdict_run_id != rows[2].verdict_run_id
    assert rows[0].report_run_id != rows[2].report_run_id
    assert rows[1].report_run_id is None
    assert len(artifacts["reports"]) == 2
    assert "upstream-secret-body" not in str(rows[1].failure_code)
    summaries = asyncio.run(get_analysis_claims(
        run.id, session, Settings(app_env="development"),
    )).claims
    assert summaries[1].result_label is None
    assert summaries[1].verdict_run_id is None


def test_report_endpoint_uses_frozen_run_and_blocks_nonproduction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, run, artifacts = asyncio.run(run_fixture(monkeypatch, (FIXTURE_TEXT,)))
    row = next(row for (kind, _), row in session.rows.items()
               if kind is ClaimAnalysisRunRecord)
    report = asyncio.run(get_claim_report(run.id, row.claim_id, session,
                                        Settings(app_env="development")))
    assert report.semantic_hash == artifacts["reports"][row.report_run_id].semantic_hash
    with pytest.raises(LensError) as blocked:
        asyncio.run(get_claim_report(run.id, row.claim_id, session,
                                     Settings(app_env="production")))
    assert blocked.value.status_code == 403
    summaries = asyncio.run(get_analysis_claims(
        run.id, session, Settings(app_env="production"),
    )).claims
    assert summaries[0].result_label is None
    assert summaries[0].production_qualified is False
    row.report_run_id = uuid4()
    with pytest.raises(LensError) as missing:
        asyncio.run(get_claim_report(run.id, row.claim_id, session,
                                     Settings(app_env="development")))
    assert missing.value.status_code == 404


def test_extraction_failure_never_invents_claims_or_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, run, artifacts = asyncio.run(run_fixture(
        monkeypatch, (FIXTURE_TEXT,), extraction_failure=True,
    ))
    assert run.status == "failed" and run.failure_code == "extracting_failed"
    assert run.claim_count == 0
    assert not any(kind is Claim for kind, _ in session.rows)
    assert not artifacts["reports"]
    assert "sensitive-extractor-body" not in run.failure_code


def test_worker_composition_failure_does_not_leave_queued_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class WorkerSession(MemorySession):
        def __enter__(self) -> "WorkerSession":
            return self

        def __exit__(self, *_: object) -> None:
            return None

    session = WorkerSession()
    run = AnalysisRunRecord(
        id=uuid4(), status="queued", stage="queued", completed_stages=[],
        stage_timestamps={}, claim_count=0, completed_claims=0,
        request_hash="a" * 64, purge_after=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(run)
    monkeypatch.setattr("app.orchestration.worker.SessionLocal", lambda: session)

    def broken_adapter(_: Settings) -> object:
        raise RuntimeError("secret adapter configuration")

    monkeypatch.setattr("app.orchestration.worker.build_orchestrator", broken_adapter)
    asyncio.run(run_background(run.id, request_for(FIXTURE_TEXT), Settings(app_env="test")))
    assert run.status == "failed"
    assert run.failure_code == "worker_initialization_failed"
    assert run.stage_timestamps["queued"]["failed_at"]
    assert "secret" not in run.failure_code


def test_zero_results_is_not_enough_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, run, artifacts = asyncio.run(run_fixture(
        monkeypatch, (FIXTURE_TEXT,), no_results=True,
    ))
    row = next(row for (kind, _), row in session.rows.items()
               if kind is ClaimAnalysisRunRecord)
    report = artifacts["reports"][row.report_run_id]
    assert run.status == "completed"
    assert report.verdict == LensVerdict.NOT_ENOUGH_EVIDENCE
    assert not row.judge_run_ids and not row.validation_run_ids
    assert not report.key_evidence


def test_one_failed_judge_is_excluded_without_corrupting_peers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _, artifacts = asyncio.run(run_fixture(
        monkeypatch, (FIXTURE_TEXT,), one_failed_judge=True,
    ))
    row = next(row for (kind, _), row in session.rows.items()
               if kind is ClaimAnalysisRunRecord)
    verdict = artifacts["verdicts"][row.verdict_run_id]
    assert len(row.judge_run_ids) == 3 and len(row.validation_run_ids) == 2
    assert verdict.qualified_judges == 2 and verdict.excluded_judges == 1
    assert verdict.verdict == LensVerdict.SUPPORTED
    assert not verdict.production_qualified


def test_validation_unavailable_abstains_as_unable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _, artifacts = asyncio.run(run_fixture(
        monkeypatch, (FIXTURE_TEXT,), unvalidated=True,
    ))
    row = next(row for (kind, _), row in session.rows.items()
               if kind is ClaimAnalysisRunRecord)
    report = artifacts["reports"][row.report_run_id]
    assert report.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert not report.key_evidence


def test_contradicted_fixture_uses_same_explicit_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _, artifacts = asyncio.run(run_fixture(
        monkeypatch, (FIXTURE_TEXT,), contradicted=True,
    ))
    row = next(row for (kind, _), row in session.rows.items()
               if kind is ClaimAnalysisRunRecord)
    report = artifacts["reports"][row.report_run_id]
    assert report.verdict == LensVerdict.CONTRADICTED
    assert "did not reduce" in report.key_evidence[0].exact_excerpt
    assert not report.production_qualified


def test_corrupt_pack_hash_fails_before_judging_or_trusted_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, run, artifacts = asyncio.run(run_fixture(
        monkeypatch, (FIXTURE_TEXT,), corrupt_pack=True,
    ))
    row = next(row for (kind, _), row in session.rows.items()
               if kind is ClaimAnalysisRunRecord)
    assert run.status == row.status == "failed"
    assert row.failure_code == "judging_failed"
    assert not row.judge_run_ids and not row.report_run_id
    assert not artifacts["reports"]


def test_report_read_never_calls_retrieval_and_rejects_modified_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, run, _ = asyncio.run(run_fixture(monkeypatch, (FIXTURE_TEXT,)))
    row = next(row for (kind, _), row in session.rows.items()
               if kind is ClaimAnalysisRunRecord)

    async def forbidden(*_: object) -> object:
        raise AssertionError("Report GET must not retrieve")

    monkeypatch.setattr("app.api.routes.analyses.retrieve_pubmed", forbidden)
    report = asyncio.run(get_claim_report(run.id, row.claim_id, session,
                                        Settings(app_env="development")))
    assert report.claim.text == FIXTURE_TEXT
    record = session.get(ReportRunRecord, row.report_run_id)
    record.result_json = {**record.result_json, "headline": "tampered"}
    with pytest.raises(LensError) as invalid:
        asyncio.run(get_claim_report(run.id, row.claim_id, session,
                                     Settings(app_env="development")))
    assert invalid.value.status_code == 503


def test_report_read_rejects_modified_evidence_pack_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, run, _ = asyncio.run(run_fixture(monkeypatch, (FIXTURE_TEXT,)))
    row = next(row for (kind, _), row in session.rows.items()
               if kind is ClaimAnalysisRunRecord)
    pack = session.get(EvidencePackRecord, row.evidence_pack_id)
    pack.snapshot_json = {**pack.snapshot_json, "selected_evidence_ids": []}
    with pytest.raises(LensError) as invalid:
        asyncio.run(get_claim_report(run.id, row.claim_id, session,
                                     Settings(app_env="development")))
    assert invalid.value.status_code == 503


def test_interrupted_run_is_failed_without_replaying_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InterruptSession(MemorySession):
        def scalars(self, _statement: object) -> list[AnalysisRunRecord]:
            return [run]

    session = InterruptSession()
    run = AnalysisRunRecord(
        id=uuid4(), status="running", stage="judging", stage_timestamps={},
        completed_stages=["extracting", "normalizing", "retrieving"],
        claim_count=1, completed_claims=0,
        request_hash="a" * 64, purge_after=datetime.now(UTC) + timedelta(hours=1),
    )
    row = ClaimAnalysisRunRecord(
        id=uuid4(), analysis_run_id=run.id, claim_id=uuid4(), ordinal=1,
        status="running", stage="judging", stage_timestamps={},
        completed_stages=["normalizing", "retrieving"],
        judge_run_ids=[], validation_run_ids=[],
    )
    session.add(run)
    session.add(row)
    monkeypatch.setattr("app.orchestration.state.claim_runs", lambda *_: [row])
    assert mark_interrupted(session) == 1
    assert run.status == row.status == "failed"
    assert run.failure_code == row.failure_code == "worker_interrupted"
    assert run.stage_timestamps["judging"]["failed_at"]
    assert row.stage_timestamps["judging"]["failed_at"]


def test_expired_run_cannot_be_read_or_resurrected() -> None:
    session = MemorySession()
    row = AnalysisRunRecord(
        id=uuid4(), status="completed", stage="completed", completed_stages=[],
        claim_count=0, completed_claims=0,
        request_hash="a" * 64, purge_after=datetime.now(UTC) - timedelta(seconds=1),
    )
    session.add(row)
    with pytest.raises(LensError) as expired:
        get_run(session, row.id)
    assert expired.value.status_code == 404
