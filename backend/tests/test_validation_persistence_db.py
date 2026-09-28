"""Optional migrated-PostgreSQL append-only and repeat-validation check."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from app.db.session import SessionLocal
from app.judging.persistence import persist_judge_runs
from app.models.claim import Claim
from app.models.enums import InputType
from app.models.judge_validation_run import JudgeValidationRunRecord
from app.models.retrieval import EvidencePackRecord, RetrievalRun
from app.models.submission import Submission
from app.validation.persistence import persist_validation_run
from app.validation.service import ValidationService
from tests.test_validation import fixture_pack, judge_for

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1",
                                reason="Set RUN_DB_TESTS=1 with migrated PostgreSQL")


def test_repeat_validation_appends_and_update_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = fixture_pack()
    judge = judge_for(pack)
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
                id=judge.evidence_pack_id, claim_id=pack.claim_id, run_id=retrieval_id,
                version="1.3", snapshot_hash=pack.snapshot_hash,
                snapshot_json=pack.model_dump(mode="json"), created_at=datetime.now(UTC),
            ))
            session.flush()
            monkeypatch.setattr(session, "commit", session.flush)
            persist_judge_runs(session, (judge,))
            first = asyncio.run(ValidationService().run(judge, pack))
            second = asyncio.run(ValidationService().run(judge, pack))
            persist_validation_run(session, first)
            persist_validation_run(session, second)
            rows = list(session.scalars(select(JudgeValidationRunRecord).where(
                JudgeValidationRunRecord.judge_run_id == judge.judge_run_id,
            )))
            assert len(rows) == 2
            assert {row.id for row in rows} == {first.id, second.id}
            assert all(row.evidence_pack_hash == pack.snapshot_hash for row in rows)
            with pytest.raises(DBAPIError, match="append-only"):
                with session.begin_nested():
                    session.execute(update(JudgeValidationRunRecord).where(
                        JudgeValidationRunRecord.id == rows[0].id,
                    ).values(status="validated"))
        finally:
            session.rollback()
