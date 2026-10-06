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


@pytest.mark.parametrize("relation_contract",
                         [False, True, "axes", "numeric_axes", "numeric_blocked", "structured",
                          "position"])
def test_repeat_validation_appends_and_update_is_blocked(
    monkeypatch: pytest.MonkeyPatch, relation_contract: bool | str,
) -> None:
    pack = fixture_pack()
    judge = judge_for(pack)
    validator = None
    if relation_contract == "position":
        import hashlib

        from app.retrieval.evidence_pack import canonical_pack_bytes
        from tests.test_validated_evidence_position import SavedChecker, position_contract, saved

        original, pack, response = saved("sunscreen")
        # New transaction-local identities; never reuse or rewrite captured rows.
        claim_id = uuid4()
        snapshot = pack.claim_snapshot.model_copy(update={"claim_id": claim_id})
        digest = hashlib.sha256(canonical_pack_bytes(
            snapshot, pack.query_plan, pack.documents, pack.passages,
            pack.selected_evidence_ids, pack_version=pack.evidence_pack_version,
        )).hexdigest()
        pack = pack.model_copy(update={"claim_id": claim_id, "claim_snapshot": snapshot,
                                       "snapshot_hash": digest})
        original = original.model_copy(update={"claim_id": claim_id, "judge_run_id": uuid4(),
            "evidence_pack_id": uuid4(), "evidence_pack_hash": digest})
        judge = position_contract(original, pack, advisory="contradicted")
        validator = SavedChecker(response)
    elif relation_contract == "structured":
        from tests.test_structured_numeric_references import OfflineChecker, structured_fixture

        judge, pack, response = structured_fixture()
        validator = OfflineChecker(response)
    elif relation_contract in {"axes", "numeric_axes", "numeric_blocked"}:
        from app.evaluation.slice41_cases import CASES, probe_judge
        from tests.test_reliability_slice4_1 import FixtureValidator

        judge, pack = probe_judge(CASES[2])
        validator = FixtureValidator(CASES[2])
        if relation_contract in {"numeric_axes", "numeric_blocked"}:
            from tests.test_numeric_fidelity_comparability import pattern

            judge, pack, response = pattern("luna")
            if relation_contract == "numeric_blocked":
                judge = judge.model_copy(update={"decision": judge.decision.model_copy(update={
                    "conclusion": judge.decision.conclusion.model_copy(update={
                        "justification": "S2 reports 20-41x risk elevation.",
                    }),
                })})

            class NumericFixture:
                provider = model = "fixture"

                async def assess_joint23(self, prepared):
                    assert relation_contract != "numeric_blocked", "Must skip semantic call"
                    return response

            validator = NumericFixture()
    elif relation_contract:
        from tests.test_reliability_slice2 import FixtureRelations, new_judge

        judge, pack = new_judge("The randomized trial measured X and Y.",
                                "The randomized trial measured X and Y.")
        validator = FixtureRelations(("insufficient",))
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
            first = asyncio.run(ValidationService(semantic_validator=validator).run(judge, pack))
            second = asyncio.run(ValidationService(semantic_validator=validator).run(judge, pack))
            persist_validation_run(session, first)
            persist_validation_run(session, second)
            rows = list(session.scalars(select(JudgeValidationRunRecord).where(
                JudgeValidationRunRecord.judge_run_id == judge.judge_run_id,
            )))
            assert len(rows) == 2
            assert {row.id for row in rows} == {first.id, second.id}
            assert all(row.evidence_pack_hash == pack.snapshot_hash for row in rows)
            if relation_contract == "position":
                from app.models.judge_run import JudgeRunRecord
                from app.validation.audit25 import audit_matches25
                from app.verdict.persistence import _judge, _validation

                stored_judge = session.get(JudgeRunRecord, judge.judge_run_id)
                session.refresh(stored_judge)
                assert stored_judge.decision_json["advisory_label"] == "contradicted"
                assert all(row.result_json["validated_evidence_position"] == "supported"
                           for row in rows)
                assert all(row.validation_version == "judge-validation-2.5" for row in rows)
                assert all(audit_matches25(_judge(stored_judge), _validation(row), pack,
                                          "standard") for row in rows)
            elif relation_contract == "structured":
                from app.models.judge_run import JudgeRunRecord
                from app.validation.audit24 import audit_matches24
                from app.verdict.persistence import _judge, _validation

                stored_judge = session.get(JudgeRunRecord, judge.judge_run_id)
                session.refresh(stored_judge)
                assert all(audit_matches24(_judge(stored_judge), _validation(row), pack,
                                          "standard") for row in rows)
                assert all(row.validation_version == "judge-validation-2.4" for row in rows)
                assert all(len(row.result_json["numeric_findings"]) == 3 for row in rows)
                assert all(n["source_quantity_id"].startswith("E1.U1.Q") for row in rows
                           for n in row.result_json["numeric_findings"])
                assert all("numeric_occurrences" not in row.result_json for row in rows)
                assert stored_judge.input_snapshot_json["source_quantity_catalog"]["version"] == (
                    "source-quantity-catalog-1.0")
            elif relation_contract in {"axes", "numeric_axes"}:
                from app.models.judge_run import JudgeRunRecord
                from app.validation.audit23 import audit_matches23
                from app.verdict.persistence import _judge, _validation

                stored_judge = session.get(JudgeRunRecord, judge.judge_run_id)
                session.refresh(stored_judge)
                assert all(audit_matches23(_judge(stored_judge), _validation(row), pack,
                                          "standard") for row in rows)
                assert all(row.validation_version == "judge-validation-2.3" for row in rows)
                assert all(row.result_json["relation_validation"]["joint_response"]["assessments"]
                           for row in rows)
                assert all(row.result_json["conclusion_qualification"]["version"] ==
                           "conclusion-qualifier-1.4" for row in rows)
                if relation_contract == "numeric_axes":
                    assert all(row.result_json["numeric_findings"] for row in rows)
                    assert all(n["fidelity"]["status"] == "verified" for row in rows
                               for n in row.result_json["numeric_findings"])
                    assert all(row.deterministic_validator_version ==
                               "source-unit+numeric-materiality-1.3+axes-1.0" for row in rows)
                    assert all(row.result_json["numeric_occurrences"] for row in rows)
            elif relation_contract == "numeric_blocked":
                assert all(row.result_json["semantic_validation"]["state"] ==
                           "skipped_due_to_numeric_preflight" for row in rows)
                assert all(row.result_json["semantic_validation"]["blocking_issue_ids"]
                           for row in rows)
                assert all(row.result_json["numeric_occurrences"] for row in rows)
                assert all(row.attempt_count == 0 for row in rows)
                assert all(row.error_category == "material_preflight_failure" for row in rows)
                assert all("No semantic attribution validator is configured."
                           not in a["reason"] for row in rows
                           for a in row.result_json["statement_attributions"])
            elif relation_contract:
                assert all(row.validation_version == "judge-validation-2.2" for row in rows)
                assert all(row.result_json["relation_validation"]["assessments"] for row in rows)
                assert all(row.result_json["conclusion_qualification"]["output"]["status"] ==
                           "justified" for row in rows)
            with pytest.raises(DBAPIError, match="append-only"):
                with session.begin_nested():
                    session.execute(update(JudgeValidationRunRecord).where(
                        JudgeValidationRunRecord.id == rows[0].id,
                    ).values(status="validated"))
        finally:
            session.rollback()
