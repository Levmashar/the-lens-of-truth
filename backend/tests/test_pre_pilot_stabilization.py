"""Source-literal intake and versioned validator engineering controls."""

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from app.adapters.claim_extractor import ExtractedClaimCandidate, PicoCandidate
from app.evaluation.slice41_cases import CASES, annotated_response, probe_judge
from app.judging.models import JudgeSlot, ProviderResponse
from app.judging.service import JudgeService
from app.medical.linker import MedicalEntityLinker
from app.medical.mesh import LocalMeshProvider
from app.medical.umls import UnconfiguredUmlsProvider
from app.pipeline.claim_types import ClaimType
from app.pipeline.completeness import assess_completeness
from app.pipeline.numeric_effect import numeric_effect
from app.pipeline.pico import NormalizedPico, normalization_status, normalize_pico
from app.pipeline.readiness import ready_for_evidence
from app.retrieval.models import ClaimSnapshot
from app.retrieval.query_planner import plan_pubmed_queries
from app.validation.audit23 import audit_matches23
from app.validation.axes import gradient_kind, mapped_relations, null_precision_reason, qualify_axes
from app.validation.joint23 import (
    normalized_references23,
    prepare_joint23,
    qualification_input23,
    validate_joint23,
)
from app.validation.models import ValidationStatus
from app.validation.numeric23 import numeric_issues23
from app.validation.relation_flow import claim_magnitude_alignment


@pytest.mark.parametrize(("source", "exposure", "outcome", "kind", "value", "unit"), [
    ("Smoking increases lung cancer risk by 85%.", "Smoking", "lung cancer risk",
     "percent_change", "85", "%"),
    ("Drug X reduces blood pressure by 20%.", "Drug X", "blood pressure",
     "percent_change", "20", "%"),
    ("Vitamin C reduces cold duration by 50%.", "Vitamin C", "cold duration",
     "percent_change", "50", "%"),
    ("Treatment X lowers mortality by 10 percentage points.", "Treatment X", "mortality",
     "percentage_points", "10", "percentage points"),
    ("Exposure X doubles the risk of Y.", "Exposure X", "risk of Y",
     "fold_change", "2", "fold"),
    ("Exposure X increases risk of Y by 2-fold.", "Exposure X", "risk of Y",
     "fold_change", "2", "fold"),
    ("Exposure X has an RR of 1.5 for Y.", "Exposure X", "Y",
     "risk_ratio", "1.5", "RR"),
])
def test_numeric_source_literal_framing(source, exposure, outcome, kind, value, unit):
    candidate = ExtractedClaimCandidate(
        raw_span=source, span_start=0, span_end=len(source), claim_type=ClaimType.CAUSAL,
        pico=PicoCandidate(intervention_or_exposure=exposure,
                           outcome=f"{outcome} increase by {value}{unit}"),
    )
    pico = normalize_pico(candidate)
    assert pico.original_claim == source
    assert pico.intervention_or_exposure == exposure
    assert pico.outcome == outcome
    assert pico.comparator is None
    assert pico.claim_type == ClaimType.CAUSAL
    assert pico.numeric_effect is not None
    assert (pico.numeric_effect.kind, pico.numeric_effect.value,
            pico.numeric_effect.unit) == (kind, value, unit)
    assert str(value) in pico.numeric_effect.raw_text or source.find("doubles") >= 0
    assert source == ClaimSnapshot(claim_id=uuid4(), raw_text=source, pico=pico).standalone_text
    plan = plan_pubmed_queries(ClaimSnapshot(claim_id=uuid4(), raw_text=source, pico=pico,
                                              claim_type=pico.claim_type))
    assert plan.queries


def test_numeric_smoking_linking_and_retrieval_readiness():
    source = "Smoking increases lung cancer risk by 85%."
    candidate = ExtractedClaimCandidate(raw_span=source, span_start=0, span_end=len(source),
        claim_type=ClaimType.CAUSAL,
        pico=PicoCandidate(intervention_or_exposure="Smoking",
                           outcome="lung cancer risk increase by 85%"))
    pico = normalize_pico(candidate)
    mesh = LocalMeshProvider({"smoking": ("D012907", "Smoking", 1.0),
                              "lung cancer": ("D008175", "Lung Neoplasms", 0.95)})
    entities = MedicalEntityLinker(mesh=mesh, umls=UnconfiguredUmlsProvider()).link(pico)
    quality = assess_completeness(pico, entities, mesh)
    status = normalization_status(pico, linked_count=sum(bool(e.mesh_id) for e in entities),
                                  mention_count=len(entities), quality=quality)
    assert {e.surface_text.casefold() for e in entities} >= {"smoking", "lung cancer"}
    assert ready_for_evidence(status, pico_json=pico.model_dump(mode="json"),
                              quality_json=quality.model_dump(mode="json"))
    plan = plan_pubmed_queries(ClaimSnapshot(claim_id=uuid4(), raw_text=source,
                                             claim_type=ClaimType.CAUSAL,
                                             pico=pico, entities=entities))
    assert any('"Lung Neoplasms"[MeSH Terms]' in q.query for q in plan.queries)


def test_malformed_numeric_phrase_retains_outcome_without_magnitude():
    source = "Drug X reduces blood pressure by roughly 2..%"
    candidate = ExtractedClaimCandidate(raw_span=source, span_start=0, span_end=len(source),
        claim_type=ClaimType.CAUSAL,
        pico=PicoCandidate(intervention_or_exposure="Drug X", outcome="lowered pressure"))
    pico = normalize_pico(candidate)
    assert pico.outcome == "blood pressure"
    assert pico.numeric_effect is not None and pico.numeric_effect.status == "uncertain"
    assert pico.numeric_effect.value is None
    assert pico.original_claim == source


def test_historical_pico_serialization_has_no_new_null_field():
    old = {"original_claim": "X increases Y.", "population": None,
           "intervention_or_exposure": "X", "comparator": None, "outcome": "Y",
           "timeframe": None, "claim_type": "causal"}
    assert NormalizedPico.model_validate(old).model_dump(mode="json") == old


def test_omitted_simple_numeric_subject_is_recovered_verbatim():
    source = "Drug X reduces blood pressure by 20%."
    candidate = ExtractedClaimCandidate(raw_span=source, span_start=0, span_end=len(source),
        claim_type=ClaimType.CAUSAL, pico=PicoCandidate(outcome="blood pressure"))
    pico = normalize_pico(candidate)
    assert pico.intervention_or_exposure == "Drug X"
    assert pico.outcome == "blood pressure"
    assert pico.comparator is None


def test_fold_claim_is_material_in_new_contract_without_percent_point_conversion():
    claim = "Exposure X doubles the risk of Y."
    assert claim_magnitude_alignment(claim, "A trial found RR 2.0 for Y.",
                                     version="numeric-effect-1.0") == "aligned"
    assert claim_magnitude_alignment(claim, "A trial found RR 1.5 for Y.",
                                     version="numeric-effect-1.0") == "mismatch"
    assert claim_magnitude_alignment(claim, "A trial found 2 percentage points more Y.",
                                     version="numeric-effect-1.0") == "uncertain"
    assert claim_magnitude_alignment(claim, "A trial found OR 2.0 for Y.",
                                     version="numeric-effect-1.0") == "uncertain"
    assert claim_magnitude_alignment(claim, "A trial found RR 2.0 for Y.") == \
        "not_applicable"  # Historical audits do not acquire the new rule.


@pytest.mark.parametrize(("source", "expected"), [
    ("RR 1.10 (95% CI 0.40-3.00), nonsignificant; imprecise.",
     "wide_or_imprecise_interval"),
    ("High-powered equivalence study ruled out material effects.",
     "source_excludes_material_effect"),
    ("A narrow interval measured harm but did not exclude the material effect.",
     "source_does_not_exclude_effect"),
    ("A narrow interval measured a statistically meaningful increase in harm.",
     "no_source_precision_signal"),
    ("No significant association was observed.", "nonsignificance_only"),
    ("Randomized X caused less Y with p<0.01.", "no_source_precision_signal"),
])
def test_null_precision_reason_is_source_grounded(source, expected):
    assert null_precision_reason((source,)) == expected


def test_gradient_dose_and_active_comparator_stay_distinct():
    assert gradient_kind(("Daily versus discretionary X found less Y.",)) == \
        "same_exposure_gradient"
    assert gradient_kind(("High-dose versus low-dose X found less Y.",)) == "dose_gradient"
    assert gradient_kind(("X versus unrelated active treatment Z found less Y.",)) == \
        "alternative_comparator"
    base = next(c for c in CASES if c.id == "sunscreen-gradient")
    judge, pack = probe_judge(base)
    inputs = qualification_input23(judge, pack, annotated_response(base), "standard")
    mislabeled = inputs.model_copy(update={"assessments": (inputs.assessments[0].model_copy(
        update={"scope_basis": "dose"}),)})
    assert mapped_relations(mislabeled)[0].materiality == "decisive"
    dose_judge, dose_pack = probe_judge(next(c for c in CASES if c.id == "narrow-dose"))
    dose_inputs = qualification_input23(dose_judge, dose_pack,
        annotated_response(next(c for c in CASES if c.id == "narrow-dose")), "standard")
    assert mapped_relations(dose_inputs)[0].materiality != "decisive"


def test_frozen_unit_id_normalization_is_exact_and_audited():
    case = next(c for c in CASES if c.id == "wide-null")
    judge, pack = probe_judge(case)
    prepared = prepare_joint23(judge, pack, str(uuid4()))
    response = annotated_response(case)
    child = response.model_copy(update={"attributions": (
        response.attributions[0].model_copy(update={"evidence_ids": ("E1.U1",)}),)})
    normalized, changes = normalized_references23(child, prepared)
    assert normalized.attributions[0].evidence_ids == ("E1",)
    assert changes[0]["rule"] == "frozen-child-evidence-1.0"
    class Validator:
        provider = "fixture"
        model = "fixture"

        async def assess_joint23(self, _prepared):
            return child

    audit = asyncio.run(validate_joint23(judge, pack, Validator()))
    assert audit.status == ValidationStatus.VALIDATED
    assert audit.result.relation_validation["id_normalizations"] == changes
    assert audit_matches23(judge, audit, pack, "standard")
    for foreign in ("E9", "E9.U1", "E1.U999"):
        bad = child.model_copy(update={"attributions": (
            child.attributions[0].model_copy(update={"evidence_ids": (foreign,)}),)})
        with pytest.raises(ValueError):
            normalized_references23(bad, prepared)

    class BadValidator:
        provider = "fixture"
        model = "fixture"

        async def assess_joint23(self, _prepared):
            return child.model_copy(update={"attributions": (
                child.attributions[0].model_copy(update={"evidence_ids": ("E9.U1",)}),)})

    failed = asyncio.run(validate_joint23(judge, pack, BadValidator()))
    assert failed.error_category == "source_id_contract_error"
    assert failed.status != ValidationStatus.VALIDATED


def test_optional_number_false_independence_recovers_only_literal_qualitative_finding():
    case = replace(next(c for c in CASES if c.id == "smoking-positive"),
        claim="Smoking increases lung cancer risk.",
        source="Smoking increased lung cancer risk. HR 1.42.",
        finding="Smoking increased lung cancer risk.",
        raw="Smoking increased lung cancer risk. HR 9.99.",
        exposure="Smoking", outcome="lung cancer")
    judge, pack = probe_judge(case)
    response = annotated_response(case)
    response = response.model_copy(update={"attributions": (
        response.attributions[0].model_copy(update={"numeric_independent": False}),)})
    assert any(i.issue_code.value.startswith("OPTIONAL_")
               for i in numeric_issues23(judge.decision, pack))
    assert qualification_input23(judge, pack, response, "standard").base.required_findings_available
    numeric_case = replace(case, claim="Smoking increases lung cancer risk by 42%.")
    numeric_judge, numeric_pack = probe_judge(numeric_case)
    numeric_inputs = qualification_input23(numeric_judge, numeric_pack, response,
                                            "standard")
    assert numeric_inputs.base.defects
    assert qualify_axes(numeric_inputs).status != "justified"


def test_successful_format_retry_retains_safe_failure_accounting():
    case = next(c for c in CASES if c.id == "smoking-positive")
    fixture_judge, pack = probe_judge(case)
    assert fixture_judge.response_json is not None

    class FirstMalformed:
        calls = 0

        async def evaluate(self, _slot, _prepared):
            self.calls += 1
            content = ("not-json" if self.calls == 1 else
                       fixture_judge.response_json["raw_model_content"])
            return ProviderResponse(content=content)

    provider = FirstMalformed()
    slot = JudgeSlot(slot=1, provider="fixture", model="fixture",
                     model_family="fixture", base_url="https://example.invalid/v1")
    runs, _ = asyncio.run(JudgeService({"fixture": provider}, axes_development=True).run(
        uuid4(), pack, (slot,), app_env="development"))
    run = runs[0]
    assert run.outcome_status == "succeeded" and run.attempt_count == 2
    assert run.response_json is not None
    assert run.response_json["attempt_failures"] == [
        {"attempt": 1, "category": "malformed_json", "retryable": True}]
    assert "not-json" not in str(run.response_json["attempt_failures"])


@pytest.mark.parametrize(("user_claim", "raw", "expected_material"), [
    ("Smoking increases lung cancer risk.", "Smoking increased lung cancer risk. HR 1.42.", False),
    ("Smoking increases lung cancer risk.", "Smoking increased lung cancer risk. HR 9.99.", False),
    ("Smoking increases lung cancer risk.", "Smoking increased lung cancer risk in 2010.", False),
    ("Smoking increases lung cancer risk by 42%.", "Smoking increased risk by 42%.", True),
    ("Smoking increases lung cancer risk by 42%.", "Smoking increased risk by 99%.", True),
    ("Smoking increases lung cancer risk by 42%.", "Smoking increased risk in 2010.", True),
])
def test_numeric_materiality_controls(user_claim, raw, expected_material):
    case = replace(next(c for c in CASES if c.id == "smoking-positive"),
        claim=user_claim, source="Smoking increased lung cancer risk. HR 1.42.",
        finding="Smoking increased lung cancer risk." if not expected_material else raw,
        raw=raw, exposure="Smoking", outcome="lung cancer")
    judge, pack = probe_judge(case)
    issues = numeric_issues23(judge.decision, pack)
    if expected_material:
        assert all(not str(i.issue_code).startswith("OPTIONAL_") for i in issues)
    else:
        assert all(str(i.issue_code).startswith("OPTIONAL_") for i in issues)
    assert numeric_effect(user_claim) is None or pack.claim_snapshot.standalone_text == user_claim
