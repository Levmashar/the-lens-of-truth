"""Optional migrated-PostgreSQL audit reproducibility and append-only check."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from app.db.session import SessionLocal
from app.judging.models import JudgeLabel
from app.judging.persistence import persist_judge_runs
from app.models.claim import Claim
from app.models.enums import InputType
from app.models.report_run import ReportRunRecord
from app.models.retrieval import EvidencePackRecord, RetrievalRun
from app.models.submission import Submission
from app.models.verdict_run import VerdictRunRecord
from app.report.persistence import build_report_for_verdict, persist_report_run
from app.validation.persistence import persist_validation_run
from app.verdict.models import LensVerdict
from app.verdict.persistence import load_aggregation_context, persist_verdict_run
from app.verdict.service import VerdictService
from tests.test_verdict import case

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1",
                                reason="Set RUN_DB_TESTS=1 with migrated PostgreSQL")


def test_verdict_runs_append_and_postgres_blocks_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, context = case((JudgeLabel.SUPPORTED, JudgeLabel.SUPPORTED))
    assert context.pack is not None
    pack = context.pack
    submission_id, retrieval_id = uuid4(), uuid4()
    with SessionLocal() as session:
        try:
            session.add(Submission(
                id=submission_id, client="api", language="en", input_type=InputType.TEXT,
                content_sha256="b" * 64, privacy_notice_version="test",
                consent_accepted=True, status="claims_extracted",
                purge_after=datetime.now(UTC) + timedelta(hours=1),
            ))
            session.flush()
            session.add(Claim(
                id=pack.claim_id, submission_id=submission_id, ordinal=1,
                raw_text=pack.claim_snapshot.raw_text, claim_type="treatment",
                risk_class="standard", coreference_uncertain=False,
                normalization_status="normalized",
            ))
            session.flush()
            session.add(RetrievalRun(
                id=retrieval_id, claim_id=pack.claim_id, source="pubmed", status="ok",
                query_plan_json={}, diagnostics_json={}, retrieved_at=datetime.now(UTC),
            ))
            session.flush()
            session.add(EvidencePackRecord(
                id=request.evidence_pack_id, claim_id=pack.claim_id, run_id=retrieval_id,
                version=pack.evidence_pack_version, snapshot_hash=pack.snapshot_hash,
                snapshot_json=pack.model_dump(mode="json"), created_at=datetime.now(UTC),
            ))
            session.flush()
            monkeypatch.setattr(session, "commit", session.flush)
            persist_judge_runs(session, context.judges)
            for validation in context.validations:
                persist_validation_run(session, validation)
            loaded = load_aggregation_context(session, request)
            result = VerdictService().aggregate(request, loaded)
            assert result.verdict == LensVerdict.SUPPORTED, result.reason_codes
            first = persist_verdict_run(session, result)
            second = persist_verdict_run(session, result)
            assert first.id != second.id
            assert first.semantic_hash == second.semantic_hash == result.semantic_hash
            rows = list(session.scalars(select(VerdictRunRecord).where(
                VerdictRunRecord.evidence_pack_id == request.evidence_pack_id,
            )))
            assert len(rows) == 2
            assert not any(row.production_qualified for row in rows)
            report = build_report_for_verdict(session, first.id)
            first_report = persist_report_run(session, report)
            second_report = persist_report_run(session, report)
            assert first_report.id != second_report.id
            assert first_report.semantic_hash == second_report.semantic_hash
            assert first_report.result_json["production_qualified"] is False
            assert first_report.result_json["verdict_explanation"]["version"] == "1.0"
            assert first_report.result_json["verdict_explanation"] == (
                second_report.result_json["verdict_explanation"]
            )
            assert first_report.result_json["verdict_explanation"]["evidence_ids"] == ["E1"]
            assert len(list(session.scalars(select(ReportRunRecord).where(
                ReportRunRecord.verdict_run_id == first.id,
            )))) == 2
            with pytest.raises(DBAPIError, match="append-only"):
                with session.begin_nested():
                    session.execute(update(ReportRunRecord).where(
                        ReportRunRecord.id == first_report.id,
                    ).values(report_version="2.0"))
            with pytest.raises(DBAPIError, match="append-only"):
                with session.begin_nested():
                    session.execute(update(VerdictRunRecord).where(
                        VerdictRunRecord.id == first.id,
                    ).values(verdict="contradicted"))
        finally:
            session.rollback()
