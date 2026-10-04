"""Offline contract checks; live semantic measurements are reported separately."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_judging import slot
from test_reliability_slice1 import unit_judge
from test_reliability_slice3 import modern_judge
from test_reliability_slice4 import setup_case

from app.evaluation.cases import benchmark_cases
from app.judging.models import ProviderResponse
from app.judging.prompt import prepare_compact_v2, prepare_judge_input
from app.judging.service import JudgeService
from app.judging.v3 import JudgeContentV3, derive_judge_position_v3
from app.validation.joint import JointResponse, check_response, prepare_joint_input, validate_joint
from app.validation.models import ValidationStatus
from app.verdict.models import AggregationContext, AggregationInput, ClaimFacts
from app.verdict.policy import POLICY_V4
from app.verdict.service import _audit_failure, _validation_failure


class FixtureJoint:
    provider = "fixture"
    model = "fixture"

    def __init__(self, *, missing: bool = False) -> None:
        self.calls = 0
        self.missing = missing

    async def assess_joint(self, prepared: object) -> JointResponse:
        self.calls += 1
        return JointResponse.model_validate_json(json.dumps({
            "attributions": [{"statement_id": "S1", "evidence_ids": ["E1"],
                              "status": "supported_by_sources", "scope_match": "exact",
                              "reason": "The frozen finding establishes this statement."}],
            "assessments": [{"statement_id": "S1", "relation": "insufficient",
                             "scope": "aligned", "materiality": "supporting",
                             "reason": "An imprecise null does not establish a direction."}],
            "missing_material_evidence": self.missing,
        }))


def modern_fixture(source: str, text: str) -> tuple:
    judge, pack = unit_judge(source, text)
    updated = modern_judge(judge, pack)
    from app.judging.source_units import materialize_content

    content = {"label": "not_enough_evidence", "statements": [{
        "statement_id": "S1", "text": text, "kind": "study_finding",
        "source_unit_ids": updated.decision.statements[0].source_unit_ids,
    }], "conclusion": {"based_on_statement_ids": ["S1"], "justification": "Limited evidence."},
               "uncertainty_reasons": []}
    return updated.model_copy(update={"decision": materialize_content(
        json.dumps(content), updated.input_snapshot_json,
    )}), pack


def test_joint_one_call_preserves_separate_targets_and_numeric_source() -> None:
    judge, pack = modern_fixture("X and Y were associated, RR 1.2 (95% CI 0.5-2.0).",
                                 "X and Y were associated.")
    validator = FixtureJoint()
    audit = asyncio.run(validate_joint(judge, pack, validator))
    assert validator.calls == audit.attempt_count == 1
    assert not audit.result.targeted_issues
    assert audit.status == ValidationStatus.VALIDATED
    prepared = prepare_joint_input(judge, pack, str(audit.id))
    data = json.loads(prepared.user_prompt.split("\n", 1)[1])
    assert "proposed_label" not in data and "conclusion" not in data
    assert "source_units" in data["frozen_snapshot"]
    assert audit.result.relation_validation["prompt_hash"] == prepared.prompt_hash


def test_missing_counterevidence_blocks_without_new_vote() -> None:
    judge, pack = modern_fixture("X and Y were associated.", "X and Y were associated.")
    audit = asyncio.run(validate_joint(judge, pack, FixtureJoint(missing=True)))
    assert audit.status == ValidationStatus.UNABLE_TO_VALIDATE
    assert audit.error_category == "missing_material_evidence"


def test_reference_or_actual_numeric_defect_prevents_paid_check() -> None:
    judge, pack = modern_fixture("X reduced Y risk with RR 0.85.",
                                 "X reduced Y risk by 85%.")
    validator = FixtureJoint()
    audit = asyncio.run(validate_joint(judge, pack, validator))
    assert validator.calls == 0
    assert audit.status == ValidationStatus.INVALID


def test_joint_reference_response_must_match_exact_input() -> None:
    judge, pack = modern_fixture("X and Y were associated.", "X and Y were associated.")
    response = asyncio.run(FixtureJoint().assess_joint(None))
    response = response.model_copy(update={"attributions": (
        response.attributions[0].model_copy(update={"evidence_ids": ("E999",)}),
    )})
    with pytest.raises(ValueError):
        check_response(response, prepare_joint_input(judge, pack, "fixture"))


def test_joint_audit_rechecks_actual_prompt_response_and_input() -> None:
    judge, pack = modern_fixture("X and Y were associated.", "X and Y were associated.")
    audit = asyncio.run(validate_joint(judge, pack, FixtureJoint()))
    request = AggregationInput(
        claim_id=pack.claim_id, evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=pack.snapshot_hash, judge_run_ids=(judge.judge_run_id,),
        judge_validation_run_ids=(audit.id,), policy_version=POLICY_V4.version,
        mode="fixture_or_evaluation",
    )
    context = AggregationContext(
        claim=ClaimFacts(claim_id=pack.claim_id, risk_class="standard",
                         normalization_status="normalized"),
        pack=pack, stored_pack_hash=pack.snapshot_hash, retrieval_status="ok",
        judges=(judge,), validations=(audit,),
    )
    assert _audit_failure(request, context) is None
    assert _validation_failure(judge, audit, POLICY_V4, evaluation_mode=True) is None
    assert _validation_failure(judge, audit, POLICY_V4, evaluation_mode=False) is not None
    for key in ("input_hash", "input_json", "joint_response"):
        relation = dict(audit.result.relation_validation)
        relation[key] = "tampered" if key == "input_hash" else {}
        altered = audit.model_copy(update={"result": audit.result.model_copy(update={
            "relation_validation": relation,
        })})
        assert _audit_failure(request, context.model_copy(update={"validations": (altered,)}))


def test_historical_joint_prompt_reconstructs_after_direction_fix() -> None:
    from app.validation.joint import LEGACY_VERSION

    judge, pack = modern_fixture("X and Y were associated.", "X and Y were associated.")
    old = prepare_joint_input(judge, pack, "audit", version=LEGACY_VERSION)
    new = prepare_joint_input(judge, pack, "audit")
    assert old.user_prompt == new.user_prompt
    assert old.prompt_hash != new.prompt_hash
    assert "NOT\nagreement with the claim" in new.system_prompt


def test_joint_timeout_fails_closed_without_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    judge, pack = modern_fixture("X and Y were associated.", "X and Y were associated.")
    async def unavailable(self: object, prepared: object) -> object:
        raise TimeoutError
    monkeypatch.setattr(FixtureJoint, "assess_joint", unavailable)
    audit = asyncio.run(validate_joint(judge, pack, FixtureJoint()))
    assert audit.status == ValidationStatus.UNABLE_TO_VALIDATE
    assert audit.attempt_count == 1 and audit.error_category == "joint_validator_unavailable"


def test_optional_numeric_format_exhaustion_never_rewrites_claims() -> None:
    pack = next(c.pack for c in benchmark_cases() if c.id == "support-trial")
    prepared = prepare_compact_v2(prepare_judge_input(uuid4(), pack))
    class NumericProvider:
        async def evaluate(self, slot: object, prepared: object) -> ProviderResponse:
            return ProviderResponse(content=json.dumps({
                "label": "supported", "statements": [{"statement_id": "S1",
                "text": "X increases Y by 25%.", "kind": "study_finding",
                "source_unit_ids": ["E1.U1"]}], "conclusion": {
                    "based_on_statement_ids": ["S1"], "justification": "S1 supports the claim."},
                "uncertainty_reasons": [],
            }))
    service = JudgeService(providers={"fake": NumericProvider()})
    run = asyncio.run(service._run_slot(pack, prepared, slot(1)))
    assert run.attempt_count == 2 and run.decision is None
    assert run.error_category == "optional_numeric_content"


def test_genuine_numeric_claim_not_subject_to_qualitative_format_guard() -> None:
    case = next(c for c in benchmark_cases() if c.id == "numeric-overclaim")
    base = prepare_judge_input(uuid4(), case.pack)
    prepared = prepare_compact_v2(base)
    assert "RESPONSE CONTRACT: Quantitative claim." in prepared.user_prompt
    assert "RESPONSE CONTRACT: Qualitative claim." not in prepared.user_prompt
    assert prepared.input_snapshot_json == base.input_snapshot_json


@pytest.mark.parametrize("identifier,changes", [
    ("wide-null", {"relation": "contradicts_claim", "reason_codes": ["IMPRECISE_NULL"]}),
    ("narrow-dose", {"scope": "compatible_but_narrower"}),
    ("conflict-positive", {"relation": "contradicts_claim", "reason_codes": ["CONFLICT"]}),
])
def test_reconstructed_v3_failure_patterns_fail_closed(identifier: str, changes: dict) -> None:
    # Reconstructed from retained aggregate diagnoses, NOT expired model responses.
    pack, prepared, content = setup_case(identifier)
    data = content.model_dump(mode="json")
    data["assessments"][0].update(changes)
    content = JudgeContentV3.model_validate_json(json.dumps(data))
    assert derive_judge_position_v3(content, prepared, pack).position is not None
    assert derive_judge_position_v3(content, prepared, pack, hardened=True).position is None
