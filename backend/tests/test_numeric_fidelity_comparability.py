"""Offline numeric plumbing regressions. Conditional source fixtures are not medical gold."""

import asyncio
import json
from dataclasses import replace

import pytest

from app.evaluation.slice41_cases import annotated_response
from app.judging.source_units import materialize_content
from app.pipeline.numeric_effect import numeric_effect
from app.validation.audit23 import audit_matches23
from app.validation.joint23 import finish_joint23, prepare_joint23, validate_joint23
from app.validation.models import NumericAlignment
from app.validation.numeric23 import PREVIOUS_VERSION, numeric_issues23
from app.validation.numeric_effects import (
    Measure,
    compare_to_claim,
    parse_quantities,
    source_fidelity,
)
from app.validation.v2 import validate_v2
from tests.test_verdict_explanation import SMOKING, fixture_report

CLAIM = "Smoking increases lung cancer risk by 85%."


def compare(source, assertion=None, claim=CLAIM):
    fidelity, overall = source_fidelity(assertion or source, (("E2", source),), claim)
    assert overall == NumericAlignment.ALIGNED
    assert fidelity and all(f.status == "verified" for f in fidelity)
    return compare_to_claim(fidelity[0], numeric_effect(claim), source, claim_scope_text=claim)


@pytest.mark.parametrize("source,status,effect", [
    ("RR 1.85", "aligned", "supports_magnitude"),
    ("RR 2.0", "aligned", "opposes_magnitude"),
    ("RR 20", "aligned", "opposes_magnitude"),
    ("RR 20 in lifelong smokers versus nonsmokers", "compatible_but_narrower", "noncomparable"),
    ("90% of lung cancers attributable to tobacco", "different_measure", "noncomparable"),
    ("HR 1.85", "different_measure", "noncomparable"),
    ("OR 1.85", "different_measure", "noncomparable"),
    ("20 times the risk", "aligned", "opposes_magnitude"),
    ("20-fold risk", "aligned", "opposes_magnitude"),
    ("20 times higher risk", "aligned", "unresolved"),
])
def test_measure_alignment_is_separate_from_source_fidelity(source, status, effect):
    comparability, actual = compare(source)
    assert comparability.status == status
    assert actual == effect
    if source == "RR 1.85":
        assert comparability.conversions
    if "times higher" in source:
        assert not comparability.conversions


@pytest.mark.parametrize("claim,effect", [
    (CLAIM, "supports_magnitude"),
    ("Smoking increases lung cancer risk by 8.5 percentage points.", "supports_magnitude"),
    ("Smoking increases lung cancer risk by 85 percentage points.", "opposes_magnitude"),
])
def test_complete_absolute_risk_pair_can_be_converted_without_metric_substitution(claim, effect):
    comparability, actual = compare("Absolute risk from 10% to 18.5%", claim=claim)
    assert comparability.status == "aligned"
    assert comparability.conversions
    assert actual == effect


def test_incomplete_absolute_risk_and_zero_baseline_cannot_supply_relative_effect():
    assert compare("Absolute risk 18.5%")[0].status == "different_measure"
    assert compare("Absolute risk from 0% to 18.5%")[1] == "unresolved"
    assert compare("Absolute risk 10% to 18.5%")[0].status == "different_measure"


@pytest.mark.parametrize("source,assertion,status", [
    ("HR 1.34", "HR 1.43", "mismatch"),
    ("No numerical estimate was reported.", "85% increase", "not_found"),
    ("90% male and 79% female lung cancers attributable to tobacco",
     "79% male and 90% female lung cancers attributable to tobacco", "mismatch"),
])
def test_wrong_and_absent_values_fail_closed(source, assertion, status):
    fidelity, overall = source_fidelity(assertion, (("E2", source),), CLAIM)
    assert any(f.status == status for f in fidelity)
    assert overall in {NumericAlignment.MISMATCH, NumericAlignment.UNCERTAIN}


@pytest.mark.parametrize("phrase,kind", [
    ("rate ratio 1.5", Measure.RATE_RATIO),
    ("absolute risk 10%", Measure.ABSOLUTE_RISK),
    ("risk difference 8.5%", Measure.RISK_DIFFERENCE),
    ("prevalence 10%", Measure.PREVALENCE),
    ("10 per 1000 person-years", Measure.INCIDENCE_RATE),
    ("10 events", Measure.EVENT_COUNT),
    ("10 days", Measure.DURATION),
    ("10 mg", Measure.DOSE),
    ("attributable 20% among the exposed", Measure.AF_EXPOSED),
])
def test_effect_measure_taxonomy(phrase, kind):
    assert kind in {q.kind for q in parse_quantities(phrase)[0]}


SOURCE = ("The risk of lung cancer development is 20-40 times higher in lifelong smokers "
          "compared to non-smokers. Tobacco use is the main cause of 90% of male and 79% of "
          "female lung cancers. Based on solid evidence, smoking causes lung cancer.")


def pattern(kind):
    case = replace(SMOKING, id=f"numeric-pattern-{kind}", source=SOURCE)
    _, _, pack, judges, _ = fixture_report(case)
    judge = judges[0]
    if kind == "claude":
        texts = [
            ("A review reports 20-40 times higher lung cancer risk in lifelong smokers, "
             "far larger than an 85% increase.",
             "Lifelong smokers have higher lung cancer risk than nonsmokers.",
             ["20-40 times higher risk in lifelong smokers versus nonsmokers"]),
            ("Smoking causes lung cancer, but no 85% figure is given.",
             "Smoking causes lung cancer, without establishing the claimed 85% magnitude.", []),
            ("90% male and 79% female lung cancers are attributable to tobacco; this is not "
             "an 85% relative increase.", "Attributable fractions are a different measure.",
             ["90% male and 79% female lung cancers attributable to tobacco"]),
        ]
        label = "contradicted"
    elif kind == "grok":
        texts = [("20-40 times higher risk or 90% of lung cancers attributable to tobacco.",
                  "20-40 times higher risk or 90% of lung cancers attributable to tobacco.", [])]
        label = "not_enough_evidence"
    else:
        texts = [("Smoking causes lung cancer, without establishing the claimed 85% magnitude.",
                  "Smoking causes lung cancer, without establishing the claimed 85% magnitude.",
                  []),
                 ("Lifelong smokers have higher risk; no 85% increase is established.",
                  "Lifelong smokers have higher risk; no 85% increase is established.",
                  ["20-40 times higher lung cancer risk in lifelong smokers versus nonsmokers"])]
        label = "not_enough_evidence"
    raw = {"label": label, "statements": [{"statement_id": f"S{i}", "text": text,
           "qualitative_finding": finding, "numeric_details": details, "numeric_dependency": False,
           "kind": "study_finding", "source_unit_ids": ["E1.U1"]}
           for i, (text, finding, details) in enumerate(texts, 1)],
           "conclusion": {"based_on_statement_ids": [f"S{i}" for i in range(1,len(texts)+1)],
                          "justification": "The claimed 85% magnitude is not established.",
                          "qualitative_justification": "The claimed magnitude is not established.",
                          "numeric_dependency": True}, "uncertainty_reasons": []}
    content = json.dumps(raw)
    decision = materialize_content(content, judge.input_snapshot_json)
    judge = judge.model_copy(update={"decision": decision, "response_json": {
        **decision.model_dump(mode="json"), "raw_model_content": content,
    }})
    response = annotated_response(case)
    attributions = tuple(response.attributions[0].model_copy(update={"statement_id": f"S{i}"})
                         for i in range(1,len(texts)+1))
    axes = []
    for i in range(1,len(texts)+1):
        causal = (kind == "claude" and i == 2) or (kind == "luna" and i == 1)
        axes.append(response.assessments[0].model_copy(update={
            "statement_id": f"S{i}", "direction": "supports_claim" if causal else "neutral",
            "scope": "aligned" if causal else "compatible_but_narrower",
            "scope_basis": "same_question" if causal else "population",
            "strength": "strong" if causal else "supporting",
        }))
    return judge, pack, response.model_copy(update={"attributions": attributions,
                                                   "assessments": tuple(axes)})


@pytest.mark.parametrize("kind", ["claude", "grok", "luna"])
def test_smoking_patterns_reach_semantics_without_changing_raw_output(kind):
    judge, pack, response = pattern(kind)
    raw_before = judge.response_json.copy()
    assert not numeric_issues23(judge.decision, pack)

    class Offline:
        provider = model = "fixture"
        calls = 0

        async def assess_joint23(self, prepared):
            self.calls += 1
            return response

    checker = Offline()
    audit = asyncio.run(validate_joint23(judge, pack, checker))
    assert checker.calls == 1
    assert audit.error_category != "material_preflight_failure"
    assert all(n["fidelity"]["status"] == "verified" for n in audit.result.numeric_findings)
    assert audit_matches23(judge, audit, pack, "standard") if audit.status == "validated" else True
    assert judge.response_json == raw_before
    if kind == "claude":
        assert any(n["comparability"]["status"] == "different_measure"
                   for n in audit.result.numeric_findings)
        assert all(n["numeric_effect"] == "noncomparable" for n in
                   audit.result.numeric_findings if n["target_id"] == "S3")
    if kind == "grok":
        assert judge.decision.statements[0].numeric_details == ()
        assert all(n["structure_status"] == "mixed_measures_in_qualitative_finding"
                   for n in audit.result.numeric_findings)
    if kind == "luna":
        assert audit.status == "validated"
        assert judge.decision.label == "not_enough_evidence"


def test_historical_numeric_audit_replays_with_original_version():
    judge, pack, response = pattern("luna")
    preflight = asyncio.run(validate_v2(judge, pack, None))
    prepared = prepare_joint23(judge, pack, str(preflight.id), numeric_version=PREVIOUS_VERSION)
    old = finish_joint23(preflight, judge, pack, response, prepared, risk_class="standard",
                         provider="fixture", model="fixture", numeric_version=PREVIOUS_VERSION)
    assert old.result.numeric_findings is None
    assert "numeric_findings" not in old.result.model_dump(mode="json")
    assert audit_matches23(judge, old, pack, "standard")


def test_unknown_numbers_and_unsupported_conversion_still_fail():
    assert source_fidelity("Risk was 1900% higher.", (("E2", "20 times higher risk"),),
                           CLAIM)[1] != NumericAlignment.ALIGNED
    assert source_fidelity("The estimate was published in 2010.", (("E2", "No date"),),
                           CLAIM)[1] == NumericAlignment.UNCERTAIN


def test_verified_noncomparable_quantity_never_powers_contradiction():
    case = replace(SMOKING, id="PAF-not-RR", label="contradicted", direction="opposes_claim",
                   source="90% of lung cancers attributable to tobacco.",
                   finding="90% of lung cancers attributable to tobacco.", role="direct")
    report = fixture_report(case)[0]
    assert report.verdict == "unable_to_verify_reliably"
    assert report.verdict_explanation.established is None
