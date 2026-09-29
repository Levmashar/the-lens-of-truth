"""Optional migrated-PostgreSQL check for append-only judge audit rows."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from app.adapters.judge import ProviderFailure
from app.db.session import SessionLocal
from app.judging.models import JudgeSlot, ProviderResponse
from app.judging.persistence import persist_judge_runs
from app.judging.service import JudgeService
from app.models.claim import Claim
from app.models.enums import InputType
from app.models.judge_run import JudgeRunRecord
from app.models.retrieval import EvidencePackRecord, RetrievalRun
from app.models.submission import Submission
from tests.test_judging import FakeProvider, decision_json, pack_for, slot

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1",
                                reason="Set RUN_DB_TESTS=1 with migrated PostgreSQL")


def test_judge_runs_append_and_keep_pack_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = pack_for()
    pack_id, submission_id, run_id = uuid4(), uuid4(), uuid4()
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
                raw_text=pack.claim_snapshot.raw_text, claim_type="causal",
                risk_class="standard", coreference_uncertain=False,
                normalization_status="normalized",
            ))
            session.flush()
            session.add(RetrievalRun(
                id=run_id, claim_id=pack.claim_id, source="pubmed", status="ok",
                query_plan_json={}, diagnostics_json={}, retrieved_at=datetime.now(UTC),
            ))
            session.flush()
            session.add(EvidencePackRecord(
                id=pack_id, claim_id=pack.claim_id, run_id=run_id,
                version="1.3", snapshot_hash=pack.snapshot_hash,
                snapshot_json=pack.model_dump(mode="json"), created_at=datetime.now(UTC),
            ))
            session.flush()
            monkeypatch.setattr(session, "commit", session.flush)
            service = JudgeService({"fake": FakeProvider()})
            first, _ = asyncio.run(service.run(pack_id, pack, (slot(1),)))
            second, _ = asyncio.run(service.run(pack_id, pack, (slot(1),)))
            class FailingProvider:
                async def evaluate(
                    self, judge_slot: JudgeSlot, prepared: object,
                ) -> ProviderResponse:
                    raise ProviderFailure("provider_error", retryable=False)

            failed, _ = asyncio.run(JudgeService({"fake": FailingProvider()}).run(
                pack_id, pack, (slot(2),),
            ))
            search_slot = slot(3).model_copy(update={
                "model": "mode-search", "search_override_active": True,
                "search_guard_bypassed": True,
            })
            bypassed, _ = asyncio.run(JudgeService({"fake": FakeProvider()}).run(
                pack_id, pack, (search_slot,), app_env="test",
                allow_search_enabled_development=True,
            ))
            bypassed_failure, _ = asyncio.run(JudgeService(
                {"fake": FailingProvider()},
            ).run(pack_id, pack, (search_slot,), app_env="test",
                  allow_search_enabled_development=True))
            protocol_payload = json.loads(decision_json())
            del protocol_payload["schema_version"]
            inferred, _ = asyncio.run(JudgeService({
                "fake": FakeProvider(json.dumps(protocol_payload)),
            }).run(pack_id, pack, (slot(1),)))
            persist_judge_runs(session, first)
            persist_judge_runs(session, second)
            persist_judge_runs(session, failed)
            persist_judge_runs(session, bypassed)
            persist_judge_runs(session, bypassed_failure)
            persist_judge_runs(session, inferred)
            rows = list(session.scalars(select(JudgeRunRecord).where(
                JudgeRunRecord.evidence_pack_id == pack_id,
            )))
            assert len(rows) == 6
            assert rows[0].id != rows[1].id
            assert {row.evidence_pack_hash for row in rows} == {pack.snapshot_hash}
            assert sum(row.decision_json is not None for row in rows) == 4
            assert sum(row.schema_version_inferred for row in rows) == 1
            assert next(
                row for row in rows if row.schema_version_inferred
            ).id == inferred[0].judge_run_id
            assert sum(row.error_category == "provider_error" for row in rows) == 2
            assert all(row.prompt_version == first[0].prompt_version for row in rows)
            bypassed_rows = [row for row in rows if row.search_guard_bypassed]
            assert len(bypassed_rows) == 2
            assert all(row.search_override_active and not row.search_isolation_verified
                       for row in bypassed_rows)
            with pytest.raises(DBAPIError, match="append-only"):
                with session.begin_nested():
                    session.execute(update(JudgeRunRecord).where(
                        JudgeRunRecord.id == rows[0].id,
                    ).values(model="altered"))
        finally:
            session.rollback()
