"""Offline software/safety controls, distinct from paid semantic measurements."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.evaluation.call_budget import PersistentModelBudget
from app.evaluation.slice41_cases import CASES, annotated_response, probe_judge
from app.judging.models import parse_stored_decision
from app.validation.audit23 import audit_matches23
from app.validation.axes import mapped_relations, qualify_axes
from app.validation.joint23 import prepare_joint23, qualification_input23, validate_joint23
from app.validation.models import ConclusionJustificationStatus, IssueCode, ValidationStatus
from app.validation.numeric23 import numeric_issues23
from app.verdict.policy import POLICY_V4
from app.verdict.service import _validation_failure


class FixtureValidator:
    provider = "fixture"
    model = "fixture"

    def __init__(self, case, *, independent=True, missing=False):
        self.case, self.calls = case, 0
        response = annotated_response(case)
        self.response = response.model_copy(update={
            "missing_material_evidence": missing,
            "attributions": (response.attributions[0].model_copy(
                update={"numeric_independent": independent}),),
        })

    async def assess_joint23(self, prepared):
        self.calls += 1
        return self.response


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_axes_stipulated_controls_and_roundtrip(case):
    judge, pack = probe_judge(case)
    validator = FixtureValidator(case)
    audit = asyncio.run(validate_joint23(judge, pack, validator))
    assert parse_stored_decision(judge.decision.model_dump(mode="json")) == judge.decision
    if case.id == "numeric-distortion":
        assert validator.calls == 0
        assert audit.status != ValidationStatus.VALIDATED
        return
    if case.id == "overstated-null":
        assert validator.calls == 1 and audit.status == ValidationStatus.INVALID
        return
    assert validator.calls == audit.attempt_count == 1
    assert audit.status == ValidationStatus.VALIDATED
    assert audit_matches23(judge, audit, pack, "standard")
    assert _validation_failure(judge, audit, POLICY_V4, evaluation_mode=True) is None
    assert _validation_failure(judge, audit, POLICY_V4, evaluation_mode=False) is not None


@pytest.mark.parametrize("raw,code", [
    ("The trial found less Y with X, HR 0.85.", None),
    ("The trial found less Y with X, HR 0.25.", IssueCode.OPTIONAL_NUMERIC_DETAIL_INVALID),
    ("The trial found less Y with X in 2010.", IssueCode.OPTIONAL_NUMERIC_DETAIL_UNCERTAIN),
])
def test_optional_numbers_never_rewrite_raw_and_require_independent_support(raw, code):
    base = next(c for c in CASES if c.id == "opposite-trial")
    case = replace(base, source="A randomized X trial found less Y, HR 0.85.", raw=raw)
    judge, pack = probe_judge(case)
    audit = asyncio.run(validate_joint23(judge, pack, FixtureValidator(case)))
    assert audit.status == ValidationStatus.VALIDATED
    assert judge.decision.statements[0].text == raw
    assert json.loads(judge.response_json["raw_model_content"])["statements"][0]["text"] == raw
    assert audit_matches23(judge, audit, pack, "standard")
    assert (code in audit.result.warnings) if code else not audit.result.warnings
    if code:
        blocked = asyncio.run(validate_joint23(
            judge, pack, FixtureValidator(case, independent=False)))
        assert blocked.status != ValidationStatus.VALIDATED


def test_source_only_numbers_are_not_assertions():
    case = next(c for c in CASES if c.id == "sunscreen-gradient")
    judge, pack = probe_judge(case)
    assert not numeric_issues23(judge.decision, pack)


def test_material_unparseable_numeric_claim_stays_blocked():
    case = replace(next(c for c in CASES if c.id == "numeric-distortion"),
                   finding="X reduced Y risk by 85% in 2010.")
    judge, pack = probe_judge(case)
    validator = FixtureValidator(case)
    audit = asyncio.run(validate_joint23(judge, pack, validator))
    assert validator.calls == 0 and audit.status != ValidationStatus.VALIDATED


def test_material_quantity_flag_and_quantitative_transformation_stay_strict():
    case = replace(next(c for c in CASES if c.id == "opposite-trial"),
                   source="The X trial reported RR 0.85 for Y.",
                   raw="Converting RR 0.85 gives 85% risk reduction.")
    judge, pack = probe_judge(case)
    assert any(i.severity == "fatal" for i in numeric_issues23(judge.decision, pack))


def test_gradient_compatibility_does_not_invent_zero_comparator_or_admit_alternative():
    case = next(c for c in CASES if c.id == "sunscreen-gradient")
    judge, pack = probe_judge(case)
    inputs = qualification_input23(judge, pack, annotated_response(case), "standard")
    assert inputs.comparator is None
    assert mapped_relations(inputs)[0].materiality == "decisive"
    assert qualify_axes(inputs).status == ConclusionJustificationStatus.JUSTIFIED
    explicit = inputs.model_copy(update={"comparator": "never use"})
    assert mapped_relations(explicit)[0].materiality != "decisive"
    alternative = inputs.model_copy(update={"assessments": (inputs.assessments[0].model_copy(
        update={"scope_basis": "active_alternative"}),)})
    assert mapped_relations(alternative)[0].materiality != "decisive"


def test_new_axes_audit_rejects_tampering_and_keeps_thresholds():
    case = next(c for c in CASES if c.id == "smoking-positive")
    judge, pack = probe_judge(case)
    audit = asyncio.run(validate_joint23(judge, pack, FixtureValidator(case)))
    for key in ("joint_response", "input_json", "input_hash"):
        relation = dict(audit.result.relation_validation)
        relation[key] = {}
        altered = audit.model_copy(update={"result": audit.result.model_copy(
            update={"relation_validation": relation})})
        assert not audit_matches23(judge, altered, pack, "standard")
    assert not audit_matches23(judge, audit, pack, "high")
    assert not audit_matches23(judge.model_copy(update={"response_json": {}}),
                              audit, pack, "standard")
    jsonb_judge = judge.model_copy(update={"input_snapshot_json": json.loads(json.dumps(
        judge.input_snapshot_json))})
    assert audit_matches23(jsonb_judge, audit, pack, "standard")


def test_missing_counterevidence_and_failed_validator_fail_closed():
    case = CASES[2]
    judge, pack = probe_judge(case)
    missing = asyncio.run(validate_joint23(judge, pack, FixtureValidator(case, missing=True)))
    assert missing.status != ValidationStatus.VALIDATED
    class Unavailable(FixtureValidator):
        async def assess_joint23(self, prepared):
            raise TimeoutError
    failed = asyncio.run(validate_joint23(judge, pack, Unavailable(case)))
    assert failed.attempt_count == 1 and failed.error_category == "joint_axes_timeout"
    assert failed.result.relation_validation["input_hash"]


def test_label_blind_single_joint_request_and_unspecified_comparator():
    judge, pack = probe_judge(CASES[1])
    prepared = prepare_joint23(judge, pack, "fixture")
    payload = json.loads(prepared.user_prompt.split("\n", 1)[1])
    assert payload["pico"]["comparator"] is None
    assert "proposed_label" not in payload and "conclusion" not in payload
    assert "Null comparator means UNSPECIFIED" in prepared.system_prompt
    assert "direction" in prepared.system_prompt and "strength" in prepared.system_prompt


def test_new_150_ledger_cannot_raise_or_reset_prior_ceiling(tmp_path: Path):
    old = PersistentModelBudget(tmp_path / "slice4.sqlite3", 120)
    old.reserve("fixture", "test")
    new = PersistentModelBudget(tmp_path / "slice41.sqlite3", 150)
    assert new.summary()["initiated"] == 0
    assert old.summary()["initiated"] == 1
    with pytest.raises(ValueError, match="cannot be changed"):
        PersistentModelBudget(tmp_path / "slice4.sqlite3", 150)


def test_conflict_preserves_both_directions_and_cannot_justify_decisive_vote():
    case = next(c for c in CASES if c.id == "opposite-trial")
    judge, pack = probe_judge(case)
    inputs = qualification_input23(judge, pack, annotated_response(case), "standard")
    opposition = inputs.assessments[0]
    support = opposition.model_copy(update={"statement_id": "S2", "direction": "supports_claim"})
    base = inputs.base.model_copy(update={
        "findings": (*inputs.base.findings, inputs.base.findings[0].model_copy(
            update={"statement_id": "S2"})),
        "based_on_statement_ids": ("S1", "S2"),
    })
    mixed = inputs.model_copy(update={"base": base, "assessments": (opposition, support)})
    assert [r.relation for r in mapped_relations(mixed)] == ["contradicts_claim", "supports_claim"]
    assert qualify_axes(mixed).status != ConclusionJustificationStatus.JUSTIFIED
    nei = mixed.model_copy(update={"base": base.model_copy(
        update={"proposed_label": "not_enough_evidence"})})
    assert qualify_axes(nei).status == ConclusionJustificationStatus.JUSTIFIED


def test_numeric_dependency_is_strict_even_when_qualitative_claim():
    case = replace(next(c for c in CASES if c.id == "opposite-trial"),
                   source="The X trial reported RR 0.85 for Y.", raw="RR 0.25 for Y.")
    judge, pack = probe_judge(case)
    decision = judge.decision.model_copy(update={"statements": (
        judge.decision.statements[0].model_copy(update={"numeric_dependency": True}),)})
    assert any(i.severity == "fatal" for i in numeric_issues23(decision, pack))


def test_false_precise_null_cannot_supply_decisive_opposition():
    case = next(c for c in CASES if c.id == "wide-null")
    judge, pack = probe_judge(case)
    inputs = qualification_input23(judge, pack, annotated_response(case), "standard")
    false_null = inputs.model_copy(update={"assessments": (inputs.assessments[0].model_copy(
        update={"direction": "opposes_claim", "strength": "strong",
                "finding_basis": "precise_null"}),)})
    assert mapped_relations(false_null)[0].relation == "insufficient"
    assert mapped_relations(false_null, version="conclusion-qualifier-1.2")[0].relation == \
        "contradicts_claim"
    assert false_null.assessments[0].direction == "opposes_claim"
    from app.validation.axes import precision_grounded

    assert not precision_grounded(("Harm cannot be excluded; equivalence was not established.",))
    assert not precision_grounded(("No precise estimates were obtained.",))
