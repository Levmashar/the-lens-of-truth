"""Regression checks from the latest retained manual runs; no paid calls."""
import asyncio
import gzip
import json
from pathlib import Path

import pytest

from app.adapters.entailment import JointResponseContractError, OpenAICompatibleEntailmentValidator
from app.judging.models import JudgeRun
from app.pipeline.numeric_effect import literal_exposure, literal_outcome, numeric_effect
from app.retrieval.models import EvidencePack
from app.validation.audit25 import audit_matches25
from app.validation.joint23 import JointResponse23, check_response23
from app.validation.joint24 import (
    finish_joint24,
    prepare_joint24,
    qualification_input24,
    validate_joint24,
)
from app.validation.numeric_effects import NumericQuantity, NumericSourceFidelity, compare_to_claim
from app.validation.position import LEGACY_VERSION, derive_position
from app.verdict.policy import POLICY_V4
from app.verdict.service import _validation_failure

ROWS = json.loads(gzip.decompress(Path(__file__).with_name("fixtures").joinpath(
    "manual_reliability_frozen.json.gz").read_bytes()))


def saved(prefix, slot=1):
    row = next(r for r in ROWS if r["claim"].startswith(prefix))
    judge = JudgeRun.model_validate_json(json.dumps(next(j for j in row["judges"]
                                                       if j["slot"] == slot)))
    audit = next(a for a in row["audits"] if a["judge_run_id"] == str(judge.judge_run_id))
    response = JointResponse23.model_validate_json(json.dumps(
        audit["result"]["relation_validation"]["joint_response"]))
    return judge, EvidencePack.model_validate(row["pack"]), response


@pytest.mark.parametrize("prefix", ["Regular vitamin", "Vitamin C reduces"])
@pytest.mark.parametrize("slot", [1, 2, 3])
def test_saved_trial_synthesis_support_and_historical_reconstruction(prefix, slot):
    judge, pack, response = saved(prefix, slot)
    data = qualification_input24(judge, pack, response, "standard")
    position = derive_position(data)
    assert position.validated_evidence_position == "supported"
    assert position.finding_design_overrides
    if prefix.startswith("Regular"):
        assert position.ignored_context_integrity_statement_ids
    old_data = qualification_input24(judge, pack, response, "standard",
                                    position_version=LEGACY_VERSION)
    old_position = derive_position(old_data, version=LEGACY_VERSION)
    assert old_position.validated_evidence_position != "supported"
    assert all(f.synthesis_randomized_trials is None for finding in old_data.base.findings
               for f in finding.evidence_design_facts)


def test_unknown_material_review_and_concern_context_still_fail_integrity():
    judge, pack, response = saved("Regular vitamin")
    data = qualification_input24(judge, pack, response, "standard")
    for status in ("unknown", "retracted", "expression_of_concern"):
        finding = data.base.findings[0]
        finding = finding.model_copy(update={"integrity_statuses": (status,),
            "evidence_design_facts": tuple(f.model_copy(update={"integrity": status})
                                           for f in finding.evidence_design_facts)})
        changed = data.model_copy(update={"base": data.base.model_copy(
            update={"findings": (finding, *data.base.findings[1:])})})
        assert derive_position(changed).validated_evidence_position is None
    findings = tuple(f.model_copy(update={"integrity_statuses": ("expression_of_concern",)})
                     if "unknown" in f.integrity_statuses else f for f in data.base.findings)
    changed = data.model_copy(update={"base": data.base.model_copy(update={"findings": findings})})
    assert derive_position(changed).validated_evidence_position is None


def test_review_title_or_observational_synthesis_does_not_supply_randomized_design():
    judge, pack, response = saved("Vitamin C reduces")
    data = qualification_input24(judge, pack, response, "standard")
    findings = tuple(f.model_copy(update={"evidence_design_facts": tuple(
        fact.model_copy(update={"synthesis_randomized_trials": None})
        for fact in f.evidence_design_facts)}) for f in data.base.findings)
    position = derive_position(data.model_copy(update={"base": data.base.model_copy(
        update={"findings": findings})}))
    assert position.validated_evidence_position == "not_enough_evidence"
    assert not position.finding_design_overrides


@pytest.mark.parametrize("notation", ["20 to 40", "20-40", "20\u201340"])
def test_explicit_fold_range_preserves_literal_and_endpoint(notation):
    claim = f"Lifelong smokers have {notation} times the lung cancer risk of non-smokers."
    effect = numeric_effect(claim)
    assert effect and effect.status == "parsed" and effect.value is None
    assert (effect.lower_value, effect.upper_value) == ("20", "40")
    assert effect.raw_text == f"{notation} times"
    assert literal_exposure(claim) == "Lifelong smokers"
    assert literal_outcome(claim, "Lifelong smokers") == "lung cancer risk"


@pytest.mark.parametrize("values,expected", [(("20", "40"), "supports_magnitude"),
    (("2", "4"), "opposes_magnitude"), (("25",), "unresolved"),
    (("30", "50"), "unresolved")])
def test_range_comparison_is_exact_or_disjoint_without_approximation(values, expected):
    quantity = NumericQuantity(values=values, kind="risk_ratio", literal="literal source RR")
    fidelity = NumericSourceFidelity(status="verified", asserted=quantity, source=quantity,
                                    source_evidence_ids=("E1",), reason="frozen")
    _, effect = compare_to_claim(fidelity, numeric_effect("risk is 20 to 40 times baseline"),
                                "risk ratio", claim_scope_text="risk is 20 to 40 times baseline")
    assert effect == expected


def test_old_numeric_shapes_and_ambiguous_fold_wording():
    old = numeric_effect("Smoking increases cancer risk by 2-fold.")
    assert old and old.direction == "increase" and old.value == "2"
    assert "lower_value" not in old.model_dump(mode="json")
    assert numeric_effect("Risk is 20 to 40 times higher.").status == "uncertain"
    assert numeric_effect("Risk is 40 to 20 times baseline.").status == "uncertain"


def test_new_audit_roundtrip_and_legacy_position_roundtrip():
    judge, pack, response = saved("Vitamin C reduces")

    class Checker:
        provider = "paratera"
        model = "saved"

        async def assess_joint23(self, prepared):
            return response

    audit = asyncio.run(validate_joint24(judge, pack, Checker()))
    assert audit.status == "validated"
    assert audit_matches25(judge, audit, pack, "standard")
    old = finish_joint24(audit, judge, pack, response,
                        prepare_joint24(judge, pack, str(audit.id),
                                        position_version=LEGACY_VERSION),
                        risk_class="standard", provider="paratera", model="saved",
                        position_version=LEGACY_VERSION)
    old_position = old.result.conclusion_qualification
    assert old_position["version"] == LEGACY_VERSION
    assert "finding_design_overrides" not in old_position


def test_transport_uses_structured_reference_check_and_retains_schema_failure(monkeypatch):
    judge, pack, response = saved("Regular vitamin")
    prepared = prepare_joint24(judge, pack, "saved")
    payload = response.model_dump(mode="json")
    units = judge.input_snapshot_json["source_units"]
    for attribution in payload["attributions"]:
        attribution["evidence_ids"] = [next(u["unit_id"] for u in units
                                            if u["evidence_id"] == eid)
                                       for eid in attribution["evidence_ids"]]

    async def completion(self, prepared, schema):
        return json.dumps(payload)

    monkeypatch.setattr(OpenAICompatibleEntailmentValidator, "_semantic_completion", completion)
    checker = OpenAICompatibleEntailmentValidator("paratera", "saved", "https://example.test", None)
    with pytest.raises(ValueError, match="Axes source references mismatch"):
        check_response23(JointResponse23.model_validate_json(json.dumps(payload)), prepared)
    checked = asyncio.run(checker.assess_joint23(prepared))
    assert checked.attributions[0].evidence_ids[0].startswith("E")
    payload["assessments"][0]["direction"] = "invalid_axis"
    with pytest.raises(JointResponseContractError) as exception:
        asyncio.run(checker.assess_joint23(prepared))
    assert exception.value.category == "joint_axes_schema_error"
    audit = asyncio.run(validate_joint24(judge, pack, checker))
    assert audit.error_category == "joint_axes_schema_error"
    relation = audit.result.relation_validation
    assert "invalid_axis" in relation["failed_response_content"]
    assert "direction" in relation["exception_message"]
    assert _validation_failure(
        judge, audit, POLICY_V4, evaluation_mode=True) == "VALIDATION_UNAVAILABLE"


@pytest.mark.parametrize("methods, expected", [
    ("We included randomized controlled trials.", True),
    ("We included non randomized trials.", None),
    ("Eligible trials were not randomized.", None),
    ("Randomized Controlled Trials as Topic", None),
    ("We included placebo-controlled observational studies.", None),
])
def test_randomized_synthesis_requires_affirmative_methods(methods, expected):
    from app.retrieval.models import AbstractSection
    from app.retrieval.sufficiency import randomized_synthesis

    _, pack, _ = saved("Vitamin C reduces")
    doc = next(d for d in pack.documents if d.document_id == "pubmed:23440782")
    doc = doc.model_copy(update={"abstract": methods,
        "abstract_sections": (AbstractSection(label="METHODS", text=methods),)})
    assert randomized_synthesis(doc) is expected


def test_randomized_review_direct_result_materiality_uses_trial_methods():
    judge, pack, response = saved("Vitamin C reduces")
    response = response.model_copy(update={"assessments": tuple(
        axis.model_copy(update={"strength": "supporting"})
        if axis.statement_id == "S1" else axis for axis in response.assessments)})
    data = qualification_input24(judge, pack, response, "standard")
    position = derive_position(data)
    assert position.validated_evidence_position == "supported"
    assert "S1" in position.design_materiality_statement_ids
    assert "uncertain" in data.base.findings[0].deterministic_relations
