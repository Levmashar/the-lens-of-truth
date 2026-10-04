"""Development diagnostics expose allowlisted audit metadata only."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.api.routes.analyses import _debug_judge_runs, _debug_model_statuses
from app.core.config import Settings
from app.models.analysis_run import AnalysisRunRecord, ClaimAnalysisRunRecord
from app.models.judge_run import JudgeRunRecord
from app.models.judge_validation_run import JudgeValidationRunRecord
from app.models.submission import Submission
from app.models.verdict_run import VerdictRunRecord
from app.schemas.analysis import DebugModelEvent


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


def test_debug_shows_only_audited_unit_id_mapping_not_raw_completion() -> None:
    claim_id, judge_id = uuid4(), uuid4()
    row = ClaimAnalysisRunRecord(
        claim_id=claim_id, judge_run_ids=[str(judge_id)], validation_run_ids=[],
    )
    judge = JudgeRunRecord(
        id=judge_id, claim_id=claim_id, slot=2, provider="fixture", model="fixture",
        model_family="fixture", outcome_status="succeeded", attempt_count=1,
        latency_ms=20, response_json={
            "raw_model_content": "private model text",
            "source_unit_id_normalizations": [{
                "statement_id": "S1", "from": "E2", "to": "E2.U1",
                "rule": "unique-frozen-parent-unit-1.0",
            }],
        },
    )
    session = Mock(spec=Session)
    session.get.side_effect = lambda model, identifier: (
        judge if model is JudgeRunRecord and identifier == judge_id else None
    )
    summary = _debug_judge_runs(session, row)[0]
    assert summary.judge_unit_id_normalizations[0]["to"] == "E2.U1"
    assert "private model text" not in summary.model_dump_json()


def test_validated_judge_can_still_be_excluded_by_aggregation() -> None:
    claim_id, judge_id, validation_id, verdict_id = (uuid4() for _ in range(4))
    row = ClaimAnalysisRunRecord(
        claim_id=claim_id, judge_run_ids=[str(judge_id)],
        validation_run_ids=[str(validation_id)], verdict_run_id=verdict_id,
    )
    judge = JudgeRunRecord(
        id=judge_id, claim_id=claim_id, slot=1, provider="fixture",
        model="fixture", model_family="fixture", outcome_status="succeeded",
        error_category=None, attempt_count=1, latency_ms=10,
    )
    validation = JudgeValidationRunRecord(
        id=validation_id, judge_run_id=judge_id, status="validated",
        error_category=None, result_json={"invalid": "fixture"},
    )
    verdict = VerdictRunRecord(id=verdict_id, result_json={
        "judge_qualifications": [{"judge_run_id": str(judge_id), "qualified": False,
                                  "exclusion_reasons": ["MODEL_IDENTITY_UNVERIFIED"]}],
    })
    records = {(JudgeRunRecord, judge_id): judge,
               (JudgeValidationRunRecord, validation_id): validation,
               (VerdictRunRecord, verdict_id): verdict}
    session = Mock(spec=Session)
    session.get.side_effect = lambda model, identifier: records.get((model, identifier))
    summary = _debug_judge_runs(session, row)[0]
    assert summary.validation_status == "validated"
    assert not summary.qualification_success
    assert summary.exclusion_reasons == ["MODEL_IDENTITY_UNVERIFIED"]


def test_debug_models_keep_historical_run_identity_after_configuration_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_id, submission_id, claim_id, judge_id = (uuid4() for _ in range(4))
    run = AnalysisRunRecord(id=analysis_id, submission_id=submission_id)
    claim_row = ClaimAnalysisRunRecord(
        claim_id=claim_id, judge_run_ids=[str(judge_id)],
    )
    submission = Submission(
        id=submission_id, extraction_provider="old_gateway",
        extraction_model="old_extractor",
    )
    judge = JudgeRunRecord(
        id=judge_id, claim_id=claim_id, slot=1, provider="old_gateway",
        model="old_judge", outcome_status="succeeded", error_category=None,
    )
    session = Mock(spec=Session)
    records = {(Submission, submission_id): submission, (JudgeRunRecord, judge_id): judge}
    session.get.side_effect = lambda model, identifier: records.get((model, identifier))
    monkeypatch.setattr(
        "app.api.routes.analyses.claim_runs", lambda _session, _id: [claim_row],
    )
    settings = Settings(
        _env_file=None, claim_extractor_provider="openai_compatible",
        claim_extractor_model="new_extractor", judge_1_provider="openai_compatible",
        judge_1_model="new_judge", judge_3_provider="openai_compatible",
        judge_3_model="DeepSeek-V3.2-Exp",
    )

    statuses = {item.role: item for item in _debug_model_statuses(
        settings, [], session, run,
    )}

    assert statuses["extraction"].model == "old_extractor"
    assert statuses["extraction"].origin == "analysis"
    assert statuses["judge_1"].model == "old_judge"
    assert statuses["judge_1"].status == "responded"
    assert statuses["judge_1"].origin == "analysis"
    assert statuses["judge_3"].model == "DeepSeek-V3.2-Exp"
    assert statuses["judge_3"].status == "not_called"
    assert statuses["judge_3"].origin == "current_configuration"


def test_debug_models_use_live_analysis_event_over_new_process_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = AnalysisRunRecord(id=uuid4(), submission_id=None)
    monkeypatch.setattr("app.api.routes.analyses.claim_runs", lambda _s, _id: [])
    settings = Settings(_env_file=None, judge_3_provider="openai_compatible",
                        judge_3_model="DeepSeek-V3.2-Exp")
    event = DebugModelEvent(
        role="judge_3", provider="openai_compatible", model="old_gemini",
        attempt=1, status="responded", failure_type=None, http_status=200,
        elapsed_ms=12, response_excerpt=None,
    )
    statuses = {item.role: item for item in _debug_model_statuses(
        settings, [event], Mock(spec=Session), run,
    )}
    assert statuses["judge_3"].model == "old_gemini"
    assert statuses["judge_3"].origin == "analysis"


def test_saved_validator_timeout_overrides_stale_calling_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validation_id = uuid4()
    run = AnalysisRunRecord(id=uuid4(), submission_id=None, status="completed")
    claim_row = ClaimAnalysisRunRecord(
        claim_id=uuid4(), judge_run_ids=[], validation_run_ids=[str(validation_id)],
    )
    audit = JudgeValidationRunRecord(
        id=validation_id, entailment_provider="paratera", entailment_model="GLM-5.2",
        validation_version="judge-validation-2.3", attempt_count=1,
        error_category="joint_axes_timeout", status="unable_to_validate",
    )
    session = Mock(spec=Session)
    session.get.return_value = audit
    monkeypatch.setattr("app.api.routes.analyses.claim_runs", lambda _s, _id: [claim_row])
    settings = Settings(_env_file=None, validator_provider="paratera",
                        validator_model="MiniMax-M3")
    event = DebugModelEvent(
        role="semantic_validator", provider="paratera", model="GLM-5.2",
        attempt=1, status="calling", failure_type=None, http_status=None,
        elapsed_ms=0, response_excerpt=None,
    )
    for events in ([event], []):
        statuses = {item.role: item for item in _debug_model_statuses(
            settings, events, session, run,
        )}
        assert statuses["semantic_validator"].model == "GLM-5.2"
        assert statuses["semantic_validator"].status == "unavailable"
        assert statuses["semantic_validator"].failure_type == "joint_axes_timeout"
        assert statuses["semantic_validator"].origin == "analysis"
