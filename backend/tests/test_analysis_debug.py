"""Development diagnostics expose allowlisted audit metadata only."""

from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy.orm import Session

from app.api.routes.analyses import _debug_judge_runs
from app.models.analysis_run import ClaimAnalysisRunRecord
from app.models.judge_run import JudgeRunRecord
from app.models.judge_validation_run import JudgeValidationRunRecord


def test_debug_judge_summary_exposes_safe_failures_without_response_content() -> None:
    claim_id = uuid4()
    judge_id = uuid4()
    validation_id = uuid4()
    row = ClaimAnalysisRunRecord(
        claim_id=claim_id, judge_run_ids=[str(judge_id)],
        validation_run_ids=[str(validation_id)],
    )
    judge = JudgeRunRecord(
        id=judge_id, claim_id=claim_id, slot=1, provider="openai_compatible",
        model="inclusionai/ling-3.0-flash", model_family="inclusionai",
        outcome_status="failed", error_category="timeout", attempt_count=2,
        latency_ms=80000, response_json={"private": "untrusted model response"},
    )
    validation = JudgeValidationRunRecord(
        id=validation_id, judge_run_id=judge_id, status="unable_to_validate",
        error_category="validator_unavailable", result_json={"private": "audit detail"},
    )
    records = {
        (JudgeRunRecord, judge_id): judge,
        (JudgeValidationRunRecord, validation_id): validation,
    }
    session = Mock(spec=Session)
    session.get.side_effect = lambda model, identifier: records.get((model, identifier))

    summary = _debug_judge_runs(session, row)

    assert len(summary) == 1
    assert summary[0].error_category == "timeout"
    assert summary[0].validation_error_category == "validator_unavailable"
    exposed = summary[0].model_dump_json()
    assert "untrusted model response" not in exposed
    assert "audit detail" not in exposed


def test_debug_judge_summary_ignores_a_different_claim() -> None:
    judge_id = uuid4()
    row = ClaimAnalysisRunRecord(
        claim_id=uuid4(), judge_run_ids=[str(judge_id)], validation_run_ids=[],
    )
    judge = JudgeRunRecord(id=judge_id, claim_id=uuid4())
    session = Mock(spec=Session)
    session.get.return_value = judge

    assert _debug_judge_runs(session, row) == []
