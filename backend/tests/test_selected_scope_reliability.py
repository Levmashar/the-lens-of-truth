"""Frozen failed runs, historical audits and generic scope/polarity adversaries."""

import gzip
import json
from pathlib import Path

import pytest

from app.adapters.claim_extractor import ExtractedClaimCandidate, PicoCandidate
from app.judging.models import JudgeRun
from app.medical.mesh import LocalMeshProvider
from app.pipeline.completeness import assess_completeness
from app.pipeline.pico import NormalizedPico, normalize_pico
from app.retrieval.models import AbstractSection, EvidencePack
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.sufficiency import (
    design_eligible,
    design_fact,
    finding_experiment,
    question_category,
)
from app.validation.audit25 import audit_matches25
from app.validation.joint23 import JointResponse23
from app.validation.joint24 import qualification_input24
from app.validation.models import JudgeValidationRun
from app.validation.polarity import checked_direction
from app.validation.position import ENDPOINT_GUARD_VERSION, derive_position
from app.validation.relationship_guards import RelationshipContext, guarded_axes

ROWS = json.loads(gzip.decompress(Path(__file__).with_name("fixtures").joinpath(
    "selected_scope_frozen.json.gz").read_bytes()))
LIVE_INITIAL = json.loads(gzip.decompress(Path(__file__).with_name("fixtures").joinpath(
    "selected_scope_live_initial.json.gz").read_bytes()))


def saved(number, slot):
    row = next(r for r in ROWS if r["number"] == number)
    judge = JudgeRun.model_validate_json(json.dumps(next(j for j in row["judges"]
                                                       if j["slot"] == slot)))
    audit = JudgeValidationRun.model_validate_json(json.dumps(next(v for v in row["validations"]
        if v["judge_run_id"] == str(judge.judge_run_id))))
    response = JointResponse23.model_validate_json(json.dumps(
        audit.result.relation_validation["joint_response"]))
    return judge, EvidencePack.model_validate(row["pack"]), response, audit


@pytest.mark.parametrize("number", [2, 3, 6, 12])
@pytest.mark.parametrize("slot", [1, 2, 3])
def test_all_original_selected_audits_reconstruct_unchanged(number, slot):
    judge, pack, _, audit = saved(number, slot)
    assert audit_matches25(judge, audit, pack, "standard")


@pytest.mark.parametrize("slot", [1, 2, 3])
def test_polarity_reversal_preserves_evidence_but_flips_the_position(slot):
    judge, pack, response, _ = saved(12, slot)
    data = qualification_input24(judge, pack, response, "standard")
    position = derive_position(data)
    assert position.validated_evidence_position == "contradicted"
    if slot == 3:
        assert position.input.assessments[0].direction == "supports_claim"
        assert "SOURCE_GROUNDED_POLARITY_CORRECTION" in position.semantic_guard_overrides["S1"]
        old = qualification_input24(judge, pack, response, "standard",
                                     position_version=ENDPOINT_GUARD_VERSION)
        assert derive_position(old, version=ENDPOINT_GUARD_VERSION).validated_evidence_position \
            == "supported"
    judge, pack, response, _ = saved(2, slot)
    assert derive_position(qualification_input24(judge, pack, response, "standard")) \
        .validated_evidence_position == "supported"


def test_existential_treatment_and_named_randomized_arm_not_universal_efficacy():
    judge, pack, response, _ = saved(6, 3)
    data = qualification_input24(judge, pack, response, "standard")
    position = derive_position(data)
    assert position.validated_evidence_position == "supported"
    trial = position.finding_design_overrides["S4"][0]
    assert trial.analysis_design == "randomized_intervention"
    assert "were randomised" in trial.experimental_assignment_text
    assert "EXISTENTIAL_TREATMENT_POPULATION_COMPATIBLE" \
        in position.semantic_guard_overrides["S4"]
    for text in ("Antibiotics treat all bacterial pneumonia.",
                 "Antibiotics can permanently cure bacterial pneumonia."):
        _, guards = guarded_axes(data.model_copy(update={"exact_claim": text}))
        assert "EXISTENTIAL_TREATMENT_POPULATION_COMPATIBLE" not in guards.get("S4", ())
    context = {**data.relationship_context, "population": "children"}
    _, guards = guarded_axes(data.model_copy(update={"relationship_context": context}))
    assert "EXISTENTIAL_TREATMENT_POPULATION_COMPATIBLE" not in guards.get("S4", ())


def test_frozen_narrative_causal_assertions_do_not_acquire_a_fictitious_trial():
    judge, pack, response, _ = saved(3, 1)
    position = derive_position(qualification_input24(judge, pack, response, "standard"))
    assert position.validated_evidence_position == "not_enough_evidence"
    assert not position.finding_design_overrides
    query = next(q for q in plan_pubmed_queries(pack.claim_snapshot).queries
                 if "question_design_recall" in q.source_fields)
    assert '"Papillomavirus Infections"[MeSH Terms]' in query.query
    assert '"Systematic Review"[Publication Type]' in query.query


@pytest.mark.parametrize("disease", ["HIV", "malaria", "hepatitis B"])
def test_transmission_relation_annotation_keeps_the_exact_disease(disease):
    text = f"{disease} is transmitted by an exposure."
    candidate = ExtractedClaimCandidate(raw_span=text, span_start=0, span_end=len(text),
        claim_type="causal", pico=PicoCandidate(intervention_or_exposure="an exposure",
                                              outcome=f"{disease} transmission"))
    assert normalize_pico(candidate).outcome == disease
    changed = candidate.model_copy(update={"pico": candidate.pico.model_copy(
        update={"outcome": "an unstated disease transmission"})})
    assert normalize_pico(changed).outcome is None


def test_laboratory_setting_is_not_a_missing_medical_entity_but_worker_exposure_is():
    row = next(r for r in ROWS if r["number"] == 9)
    pico = NormalizedPico.model_validate(row["pico"])
    mesh = LocalMeshProvider({"laboratory": ("D007755", "Laboratories", 0.95)})
    quality = assess_completeness(pico, (), mesh)
    assert not quality.missing_explicit_concepts and not quality.required_slots_missing
    text = "Laboratory workers develop disease."
    pico = NormalizedPico(original_claim=text, intervention_or_exposure="workers",
                          outcome="disease", claim_type="causal")
    assert assess_completeness(pico, (), mesh).missing_explicit_concepts == ("Laboratory",)


@pytest.mark.parametrize("source,expected", [
    ("Factor X increases disease Y.", "opposes_claim"),
    ("Factor X lowers disease Y.", "supports_claim"),
    ("Factor X does not increase disease Y.", None),
    ("Factor X increases disease Y but Factor X also lowers disease Y.", None),
    ("Lowering Factor X lowers disease Y.", None),
    ("Factor X increases another disease.", None),
    ("There was no significant association of Factor X with disease Y.", None),
])
def test_literal_polarity_requires_unambiguous_sourced_subject_relation_endpoint(
    source, expected,
):
    context = RelationshipContext(exposure_terms=("Factor X",), outcome_terms=("disease Y",),
                                  finding_texts={}, disease_onset=True)
    assert checked_direction("Factor X lowers disease Y.", source,
                             (source,), context) == expected


def test_trial_assignment_does_not_randomize_measured_risk_factor():
    _, pack, _, _ = saved(6, 3)
    doc = next(d for d in pack.documents if d.pmid == "37182534")
    fact = design_fact(doc)
    assert finding_experiment(fact, doc, pack.claim_snapshot,
                             "Smoking predicted pneumonia among participants.") == fact
    doc = doc.model_copy(update={"abstract_sections": (AbstractSection(label="METHODS",
        text="Patients were non-randomized to Drug A or Drug B."),)})
    assert finding_experiment(fact, doc, pack.claim_snapshot, "Drug A reduced mortality.") == fact


def test_laboratory_experiment_design_cannot_supply_clinical_causal_eligibility():
    _, pack, _, _ = saved(6, 3)
    claim = pack.claim_snapshot.model_copy(update={
        "raw_text": "Light induces apoptosis in cell lines.",
        "normalized_text": None, "pico": NormalizedPico(
            original_claim="Light induces apoptosis in cell lines.", claim_type="causal",
            population="cell lines", intervention_or_exposure="Light", outcome="apoptosis"),
        "entities": ()})
    doc = pack.documents[0].model_copy(update={"study_design": "in_vitro", "abstract_sections": (
        AbstractSection(
            text="Cell lines were exposed to light. Untreated control cells were tested."),)})
    fact = finding_experiment(design_fact(doc).model_copy(update={"role": "direct"}),
                              doc, claim, "Light induced apoptosis in cell lines.")
    assert question_category(claim, experimental_setting=True) == "laboratory_experiment"
    assert design_eligible("laboratory_experiment", fact)
    assert not design_eligible("intervention_causality", fact)
    no_controls = doc.model_copy(update={"abstract_sections": (
        AbstractSection(text="Cell lines were exposed to light."),)})
    assert finding_experiment(design_fact(no_controls), no_controls, claim,
                              "Light induced apoptosis.").experimental_assignment_text is None


@pytest.mark.parametrize("row", LIVE_INITIAL, ids=lambda r: str(r["number"]))
@pytest.mark.parametrize("slot", [1, 2, 3])
def test_initial_live_position_15_reconstructs_and_lab_endpoint_uses_actual_intervention(row, slot):
    judge = JudgeRun.model_validate_json(json.dumps(next(j for j in row["judges"]
                                                       if j["slot"] == slot)))
    audit = JudgeValidationRun.model_validate_json(json.dumps(next(v for v in row["validations"]
        if v["judge_run_id"] == str(judge.judge_run_id))))
    pack = EvidencePack.model_validate(row["pack"])
    assert audit_matches25(judge, audit, pack, "standard")
    response = JointResponse23.model_validate_json(json.dumps(
        audit.result.relation_validation["joint_response"]))
    result = derive_position(qualification_input24(judge, pack, response, "standard"))
    if row["number"] == 9:
        assert result.validated_evidence_position == "supported"
        assert result.input.base.question_category == "laboratory_experiment"
        fact = result.input.base.findings[0].evidence_design_facts[0]
        assert fact.analysis_design == "laboratory_intervention"
        assert "treated by blue light" in fact.experimental_assignment_text
        assert not design_eligible("intervention_causality", fact)
    else:
        assert result.validated_evidence_position == audit.result.validated_evidence_position


@pytest.mark.parametrize("text", [
    "In this study, cells will be exposed to light.",
    "We reviewed whether light induced apoptosis in cells in vitro.",
    "Light may induce apoptosis in cells under laboratory conditions.",
])
def test_laboratory_future_or_background_is_not_an_actual_exposure_intervention(text):
    _, pack, _, _ = saved(6, 3)
    claim = pack.claim_snapshot.model_copy(update={"pico": NormalizedPico(
        original_claim="Light induces apoptosis in cell lines.", population="cell lines",
        intervention_or_exposure="light", outcome="apoptosis"), "entities": ()})
    doc = pack.documents[0].model_copy(update={"study_design": "unknown", "abstract_sections": (
        AbstractSection(text=text),)})
    fact = finding_experiment(design_fact(doc), doc, claim, "Light induced apoptosis in cells.",
                              laboratory_intervention=True)
    assert fact.experimental_assignment_text is None
