"""Reconstructed public regression fixtures; actual retained replay is separate."""

import asyncio
import json

import pytest

from app.pipeline.numeric_effect import numeric_effect
from app.validation.audit23 import audit_matches23
from app.validation.joint23 import finish_joint23, prepare_joint23, validate_joint23
from app.validation.models import NumericAlignment
from app.validation.numeric23 import (
    FIDELITY_VERSION,
    VERSION,
    material_issue,
    numeric_issues23,
)
from app.validation.numeric_effects import (
    Measure,
    compare_to_claim,
    parse_quantities,
    source_fidelity,
)
from app.validation.numeric_occurrences import occurrences
from app.validation.v2 import validate_v2
from tests.test_numeric_fidelity_comparability import CLAIM, SOURCE, pattern

GROK = ("S1 reports 20-40x risk elevation; S2 and S3 confirm causation without "
        "the claimed magnitude.")
CLAUDE = ("Smoking is a established cause of lung cancer (S2). However, the reported relative "
          "risk in lifelong smokers is 20-40 times that of non-smokers (S1), far above an "
          "85% increase. Attributable fractions of 79-90% (S3) are a different metric. "
          "The claimed 85% increase in risk is therefore not supported by the sources "
          "and is contradicted in magnitude.")


@pytest.mark.parametrize("text", [GROK, CLAUDE])
def test_exact_documented_conclusions_pass_numeric_preflight(text):
    judge, pack, _ = pattern("claude")
    decision = judge.decision.model_copy(update={
        "conclusion": judge.decision.conclusion.model_copy(update={
            "justification": text, "qualitative_justification": text,
        }),
    })
    assert not numeric_issues23(decision, pack)
    before = numeric_issues23(decision, pack, version=FIDELITY_VERSION)
    assert [i.target_id for i in before] == ["conclusion"]


@pytest.mark.parametrize("assertion,values", [
    ("20x risk", ("20",)), ("20× risk", ("20",)), ("20 x risk", ("20",)),
    ("20-40x risk", ("20", "40")), ("20–40× risk", ("20", "40")),
    ("20–40 times the risk", ("20", "40")),
    ("2.25 – 3.75 x risk elevation", ("2.25", "3.75")),
    ("12.5 to 18.75× risk", ("12.5", "18.75")),
])
def test_risk_shorthand_has_one_typed_quantity_and_exact_original_span(assertion, values):
    source = f"{'-'.join(values)} times higher risk"
    found, residual = parse_quantities(assertion)
    assert len(found) == 1
    assert found[0].kind == Measure.FOLD_CHANGE
    assert found[0].values == values
    assert assertion[found[0].start:found[0].end] == found[0].literal
    fidelity, status = source_fidelity(assertion, (("E1", source),), CLAIM)
    assert status == NumericAlignment.ALIGNED
    assert fidelity[0].source.normalization_reason == (
        "literal_times_higher_no_arithmetic_convention")
    comparable, effect = compare_to_claim(fidelity[0], numeric_effect(CLAIM), source)
    assert effect == "unresolved"
    assert not comparable.conversions
    assert not fidelity[0].conversions


@pytest.mark.parametrize("assertion", [
    "19x risk", "20-41x risk", "19-40× risk", "2.25–3.76x risk",
])
def test_changed_risk_values_are_rejected(assertion):
    _, status = source_fidelity(assertion, (("E1", "20-40 times higher risk"),), CLAIM)
    assert status != NumericAlignment.ALIGNED


@pytest.mark.parametrize("text", [
    "20x microscope magnification", "20 × 40 dimensions", "20 x mg dose",
    "20× magnification. Risk is higher.", "Dose 20 x daily",
    "20× magnification to assess risk.",
    "Risk is screened under 20× magnification.",
])
def test_unrelated_x_context_is_not_a_risk_multiple(text):
    assert not any(q.kind == Measure.FOLD_CHANGE and q.unit == "risk_multiple"
                   for q in parse_quantities(text)[0])
    assert source_fidelity(text, (("E1", "No dose or dimension estimate."),), CLAIM)[1] \
        != NumericAlignment.ALIGNED


@pytest.mark.parametrize("text", [
    "The claimed 85% increase is not supported.",
    "The user's 85% figure is unresolved.",
    "The evidence does not establish the claimed 85%.",
    "Not the claimed 85% increase.",
    "Far above an 85% increase.",
    "The claimed 85% increase is a question to evaluate.",
    "The claim's exact 85% increase is unresolved.",
])
def test_explicit_occurrence_reference_is_bound_to_the_actual_claim(text):
    reference = [o for o in occurrences(text, CLAIM) if o.role != "identifier"]
    assert len(reference) == 1
    assert reference[0].role == "claim_reference"
    assert reference[0].reference_status == "matched"
    assert reference[0].measure_hint == "percent_change"
    assert text[reference[0].start:reference[0].end] == reference[0].literal
    assert source_fidelity(text, (("E1", "90% attributable to tobacco."),), CLAIM)[1] \
        == NumericAlignment.NOT_APPLICABLE


@pytest.mark.parametrize("value", ["12", "37.5", "92"])
def test_reference_matching_is_not_specific_to_85(value):
    claim = f"Exposure increases risk by {value}%."
    text = f"The claimed {value}% increase is unresolved."
    assert occurrences(text, claim)[0].reference_status == "matched"
    assert occurrences("The claimed 58% increase is unresolved.", claim)[0].reference_status \
        == "mismatch"


@pytest.mark.parametrize("text", [
    "The study reported an 85% increase.",
    "The study confirms the claimed 85% increase.",
    "The source did not find an 85% increase.",
    'The study reported "85% increase".',
    "The study did not report an 85% increase.",
    "The evidence confirms the claimed 85% increase.",
    "The claimed 85% increase in risk is supported by the study.",
])
def test_asserted_source_support_is_never_masked_by_claim_or_negation(text):
    assert occurrences(text, CLAIM)[0].role == "source_assertion"
    assert source_fidelity(text, (("E1", "90% attributable to tobacco."),), CLAIM)[1] \
        != NumericAlignment.ALIGNED
    assert source_fidelity(text, (("E1", "An 85% increase was reported."),), CLAIM)[1] \
        == NumericAlignment.ALIGNED
    # Last assertion checks literal fidelity only, not truth of a negated inference.


@pytest.mark.parametrize("text", [
    "The claimed 58% increase is not supported.",
    "The user's 58% figure is unresolved.",
    "The claimed 85 percentage points is unresolved.",
    "The claimed 85% decrease is unresolved.",
    "The claimed 85% attributable fraction is unresolved.",
])
def test_wrong_claim_value_or_measure_fails_closed(text):
    assert source_fidelity(text, (("E1", "58% increase"),), CLAIM)[1] \
        != NumericAlignment.ALIGNED
    assert occurrences(text, CLAIM)[0].reference_status != "matched"


def test_same_number_can_be_a_source_assertion_and_separate_claim_reference():
    text = "The study reported an 85% increase. The claimed 85% increase is unresolved."
    found = occurrences(text, CLAIM)
    assert [o.role for o in found] == ["source_assertion", "claim_reference"]
    fidelity, status = source_fidelity(text, (("E1", "90% attributable to tobacco."),), CLAIM)
    assert len(fidelity) == 1
    assert status != NumericAlignment.ALIGNED


@pytest.mark.parametrize("text", [
    "Attributable fractions of 79–90% are a different metric. "
    "The claimed 85% increase is not supported.",
    "The claimed 85% increase is not supported. "
    "Attributable fractions of 79–90% are a different metric.",
    "OR 1.85 and HR 1.85 are different metrics. The claimed 85% increase is unresolved.",
    "90% of cancers are attributable to tobacco; the claimed 85% increase is unresolved.",
])
def test_claim_reference_does_not_inherit_an_adjacent_source_measure(text):
    found = occurrences(text, CLAIM)
    ref = next(o for o in found if o.role == "claim_reference")
    assert ref.measure_hint == "percent_change"
    fidelity, status = source_fidelity(text, (("E1", SOURCE + " OR 1.85; HR 1.85."),), CLAIM)
    assert status == NumericAlignment.ALIGNED
    assert not any(f.asserted.values == ("85",) for f in fidelity)


def test_same_value_different_measures_stay_distinct_in_one_sentence():
    text = "85% of cancers attributable to tobacco, compared with an 85% increase in risk."
    kinds = [q.kind for q in parse_quantities(text)[0]]
    assert set(kinds) == {Measure.PAF, Measure.PERCENT_CHANGE}
    fidelity, _ = source_fidelity(
        text, (("E1", "85% of cancers attributable to tobacco."),), CLAIM)
    assert any(f.status != "verified" and f.asserted.kind == Measure.PERCENT_CHANGE
               for f in fidelity)


def test_identifiers_are_explicit_occurrences_not_source_statistics():
    text = "S1 and S2 cite E2.U1 and E33. No estimate is given."
    assert all(o.role == "identifier" for o in occurrences(text, CLAIM))
    assert [o.literal for o in occurrences(text, CLAIM)] == ["S1", "S2", "E2.U1", "E33"]
    assert source_fidelity(text, (("E1", "No estimates."),), CLAIM)[1] \
        == NumericAlignment.NOT_APPLICABLE


def test_statement_dependency_restricts_matching_to_actual_citation():
    sources = (("E1", "10-20 times higher risk"), ("E2", "20-40 times higher risk"))
    text = "S1 reports 20-40x risk elevation."
    mapping = {"S1": (sources[0],), "S2": (sources[1],)}
    fidelity, status = source_fidelity(text, sources, CLAIM, statement_sources=mapping)
    assert status == NumericAlignment.MISMATCH
    assert fidelity[0].source_evidence_ids == ("E1",)
    assert fidelity[0].asserted.linked_statement_id == "S1"
    assert source_fidelity("S9 reports 20-40x risk.", sources, CLAIM,
                           statement_sources=mapping)[1] != NumericAlignment.ALIGNED


def test_paf_range_needs_both_endpoints_in_one_frozen_citation():
    text = "Attributable fractions of 79–90% are a different metric."
    assert source_fidelity(text, (("E1", "79% attributable."),
                                  ("E2", "90% attributable.")), CLAIM)[1] \
        != NumericAlignment.ALIGNED
    assert source_fidelity(text, (("E1", "79% attributable."),
                                  ("E1", "90% attributable.")), CLAIM)[1] \
        != NumericAlignment.ALIGNED
    assert source_fidelity(text, (("E1", "79% female and 90% male attributable."),), CLAIM)[1] \
        == NumericAlignment.ALIGNED


def test_unknown_roles_remain_explicit_and_cannot_establish_absence_of_support():
    text = "No source supports 85%."
    assert occurrences(text, CLAIM)[0].role == "ambiguous"
    assert source_fidelity(text, (("E1", "RR 1.85"),), CLAIM)[1] == NumericAlignment.UNCERTAIN


@pytest.mark.parametrize("text", [
    "Risk was 1900% higher.", "Converted to a 2000% increase.",
    "S1 reports 20-41x risk elevation.",
])
def test_new_unsupported_conclusion_quantity_is_material_even_with_false_dependency(text):
    judge, pack, _ = pattern("claude")
    decision = judge.decision.model_copy(update={"conclusion": judge.decision.conclusion.model_copy(
        update={"justification": text, "qualitative_justification": text,
                "numeric_dependency": False})})
    issues = numeric_issues23(decision, pack)
    assert issues
    assert any(material_issue(i) for i in issues)


def test_male_female_bindings_are_preserved_and_swaps_rejected():
    fidelity, status = source_fidelity(
        "90% male and 79% female lung cancers attributable to tobacco.", (("E1", SOURCE),), CLAIM)
    assert status == NumericAlignment.ALIGNED
    assert {f.asserted.binding for f in fidelity} == {"male", "female"}
    assert source_fidelity("79% male and 90% female lung cancers attributable to tobacco.",
                           (("E1", SOURCE),), CLAIM)[1] == NumericAlignment.MISMATCH


def test_verified_literals_do_not_establish_scope_or_allow_paf_rr_substitution():
    fidelity, _ = source_fidelity("20-40x risk", (("E1", SOURCE),), CLAIM)
    comparability, effect = compare_to_claim(fidelity[0], numeric_effect(CLAIM), SOURCE)
    assert comparability.status == "compatible_but_narrower"
    assert effect == "noncomparable"
    paf, _ = source_fidelity("90% male lung cancers attributable to tobacco.",
                            (("E1", SOURCE),), CLAIM)
    assert compare_to_claim(paf[0], numeric_effect(CLAIM), SOURCE)[0].status == "different_measure"


@pytest.mark.parametrize("kind", ["grok", "claude", "luna"])
def test_offline_checker_boundary_preserves_raw_fields_and_proposed_labels(kind):
    judge, pack, _ = pattern("claude" if kind != "luna" else "luna")
    if kind != "luna":
        judge = judge.model_copy(update={"decision": judge.decision.model_copy(update={
            "conclusion": judge.decision.conclusion.model_copy(update={
                "justification": GROK if kind == "grok" else CLAUDE})})})
    original = json.dumps(judge.model_dump(mode="json"), sort_keys=True)
    source_original = pack.model_dump(mode="json")

    class Boundary:
        provider = model = "offline-boundary-double"
        calls = 0

        async def assess_joint23(self, prepared):
            self.calls += 1
            raise RuntimeError("Boundary only; no semantic evaluation")

    checker = Boundary()
    audit = asyncio.run(validate_joint23(judge, pack, checker))
    assert checker.calls == 1
    assert audit.error_category == "joint_axes_validator_unavailable"
    assert audit.result.numeric_occurrences
    assert json.dumps(judge.model_dump(mode="json"), sort_keys=True) == original
    assert pack.model_dump(mode="json") == source_original


def test_blocked_semantics_records_skip_with_actual_blocking_issues():
    judge, pack, _ = pattern("claude")
    decision = judge.decision.model_copy(update={"conclusion": judge.decision.conclusion.model_copy(
        update={"justification": "S1 reports 20-41x risk elevation."})})
    judge = judge.model_copy(update={"decision": decision})

    class NeverCalled:
        provider = model = "configured-fixture"

        async def assess_joint23(self, prepared):
            raise AssertionError("Must be skipped")

    audit = asyncio.run(validate_joint23(judge, pack, NeverCalled()))
    assert audit.attempt_count == 0
    assert audit.error_category == "material_preflight_failure"
    skip = audit.result.semantic_validation
    assert skip["state"] == "skipped_due_to_numeric_preflight"
    assert skip["blocking_issue_ids"]
    assert all("not configured" not in a.reason.lower() for a in
               audit.result.statement_attributions)
    assert all(a.reason == "skipped_due_to_numeric_preflight" for a in
               audit.result.statement_attributions)
    assert audit.result.conclusion_justification.reason == "skipped_due_to_numeric_preflight"
    missing = asyncio.run(validate_joint23(judge, pack, None))
    assert missing.result.semantic_validation is None
    assert any("No semantic attribution validator is configured." == a.reason
               for a in missing.result.statement_attributions)


def test_historical_12_exact_failures_and_omitted_new_fields_are_replayable():
    judge, pack, response = pattern("luna")
    preflight = asyncio.run(validate_v2(judge, pack, None))
    prepared = prepare_joint23(judge, pack, str(preflight.id), numeric_version=FIDELITY_VERSION)
    historical = finish_joint23(preflight, judge, pack, response, prepared, risk_class="standard",
                                provider="fixture", model="fixture",
                                numeric_version=FIDELITY_VERSION)
    assert historical.result.numeric_occurrences is None
    assert "numeric_occurrences" not in historical.result.model_dump(mode="json")
    assert all(f["version"] == "numeric-fidelity-comparability-1.0"
               for f in historical.result.numeric_findings)
    assert audit_matches23(judge, historical, pack, "standard")
    current_prepared = prepare_joint23(judge, pack, str(preflight.id), numeric_version=VERSION)
    assert current_prepared.user_prompt != prepared.user_prompt
