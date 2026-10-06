"""Frozen manual cases plus generic adversarial controls; no network calls."""

import gzip
import json
from pathlib import Path

import pytest

from app.adapters.claim_extractor import ExtractedClaimCandidate, PicoCandidate
from app.judging.models import JudgeRun
from app.pipeline.pico import normalize_pico
from app.retrieval.models import AbstractSection, EvidencePack
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import _atomic_aliases, _atomic_coverage
from app.retrieval.sufficiency import completed_trial_synthesis
from app.validation.joint23 import JointResponse23
from app.validation.joint24 import qualification_input24
from app.validation.position import TRIAL_METHOD_VERSION, derive_position
from app.validation.relationship_guards import guarded_axes

ROWS = json.loads(
    gzip.decompress(
        Path(__file__).with_name("fixtures").joinpath("manual_11_15_frozen.json.gz").read_bytes()
    )
)


def saved(prefix, slot=1):
    row = next(c for r in ROWS for c in r["claims"] if c["claim"].startswith(prefix))
    judge = JudgeRun.model_validate_json(
        json.dumps(next(j for j in row["judges"] if j["slot"] == slot))
    )
    audit = next(a for a in row["audits"] if a["judge_run_id"] == str(judge.judge_run_id))
    response = JointResponse23.model_validate_json(
        json.dumps(audit["result"]["relation_validation"]["joint_response"])
    )
    return judge, EvidencePack.model_validate(row["pack"]), response


@pytest.mark.parametrize("slot", [1, 2, 3])
def test_frozen_bp_stroke_completed_randomized_result_is_eligible(slot):
    judge, pack, response = saved("High blood pressure increases", slot)
    data = qualification_input24(judge, pack, response, "standard")
    position = derive_position(data)
    assert position.validated_evidence_position == "supported"
    assert "CAUSAL_DESIGN_INSUFFICIENT" not in position.output.reason_codes
    assert position.finding_design_overrides
    assert any(
        f.analysis_design == "causal_evidence_synthesis"
        for facts in position.finding_design_overrides.values()
        for f in facts
    )
    doc = next(d for d in pack.documents if d.pmid == "31243539")
    assert doc.study_design == "review" and doc.relationship_analysis.analysis_design == "unknown"
    old_data = qualification_input24(
        judge, pack, response, "standard", position_version=TRIAL_METHOD_VERSION
    )
    assert (
        derive_position(old_data, version=TRIAL_METHOD_VERSION).validated_evidence_position
        == "not_enough_evidence"
    )


@pytest.mark.parametrize("prefix", ["Blue light", "High blood pressure causes", "Carrots"])
@pytest.mark.parametrize("slot", [1, 2, 3])
def test_frozen_context_remains_nei_with_auditable_guards(prefix, slot):
    judge, pack, response = saved(prefix, slot)
    position = derive_position(qualification_input24(judge, pack, response, "standard"))
    assert position.validated_evidence_position == "not_enough_evidence"
    if prefix != "Carrots":
        assert position.semantic_guard_overrides


@pytest.mark.parametrize(
    "verb,annotation",
    [
        ("cures", "cured"),
        ("treats", "treated"),
        ("prevents", "prevented"),
        ("reverses", "reversed"),
    ],
)
@pytest.mark.parametrize("proposal", ["annotated", "missing"])
def test_relation_annotation_preserves_literal_disease(verb, annotation, proposal):
    text = f"An intervention {verb} type 2 diabetes in adults."
    candidate = ExtractedClaimCandidate(
        raw_span=text,
        span_start=0,
        span_end=len(text),
        claim_type="treatment",
        pico=PicoCandidate(
            intervention_or_exposure="An intervention",
            outcome=f"type 2 diabetes ({annotation})" if proposal == "annotated" else None,
        ),
    )
    pico = normalize_pico(candidate)
    assert pico.outcome == "type 2 diabetes"
    assert pico.original_claim == text


def test_disease_qualifier_is_not_stripped_as_if_it_were_a_relation_annotation():
    text = "An intervention treats diabetes."
    candidate = ExtractedClaimCandidate(
        raw_span=text,
        span_start=0,
        span_end=len(text),
        claim_type="treatment",
        pico=PicoCandidate(intervention_or_exposure="An intervention", outcome="diabetes (type 2)"),
    )
    assert (
        normalize_pico(candidate).outcome == "diabetes"
    )  # Recovery from source, not invented type.


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Randomized clinical trials have demonstrated reduced disease incidence.",
            True,
        ),
        ("Randomized trials will test whether treatment reduces disease incidence.", None),
        ("Non-randomized trials have demonstrated a reduced incidence.", None),
        ("Randomized trials have not demonstrated a reduced incidence.", None),
        ("Randomized trials have shown inconsistent effects on incidence.", None),
        ("Randomized Controlled Trials as Topic", None),
    ],
)
def test_review_requires_an_explicit_completed_affirmative_trial_result(text, expected):
    _, pack, _ = saved("High blood pressure increases")
    doc = next(d for d in pack.documents if d.pmid == "31243539")
    doc = doc.model_copy(
        update={
            "abstract": text,
            "abstract_sections": (AbstractSection(label="ABSTRACT", text=text),),
        }
    )
    assert completed_trial_synthesis(doc) is expected


@pytest.mark.parametrize(
    "kind,source,text,code",
    [
        (
            "alternative",
            "Another factor causes the disease.",
            "Another known cause is established.",
            "CLAIMED_EXPOSURE_NOT_ESTABLISHED",
        ),
        (
            "omission",
            "The exposure causes a different endpoint.",
            "The source does not mention the disease.",
            "CLAIMED_ENDPOINT_NOT_ESTABLISHED",
        ),
        (
            "ecological",
            "Global burden trends rank exposure highly while disease mortality declines.",
            "Disease mortality declined over the same period.",
            "ECOLOGICAL_TREND_IS_CONTEXT",
        ),
        (
            "cells",
            "Exposure kills existing disease cells.",
            "Exposure kills existing disease cells.",
            "DISEASE_STAGE_ENDPOINT_MISMATCH",
        ),
        (
            "diagnostic",
            "Exposure is used in diagnostic detection of disease.",
            "Exposure is used in diagnostic detection of disease.",
            "DISEASE_STAGE_ENDPOINT_MISMATCH",
        ),
        (
            "progression",
            "Exposure slows progression of existing disease.",
            "Exposure slows progression of existing disease.",
            "DISEASE_STAGE_ENDPOINT_MISMATCH",
        ),
    ],
)
def test_invalid_contradiction_cannot_be_made_material_by_validator_strength(
    kind, source, text, code
):
    judge, pack, response = saved("High blood pressure causes")
    data = qualification_input24(judge, pack, response, "standard")
    axis = data.assessments[0].model_copy(
        update={
            "direction": "opposes_claim",
            "scope": "aligned",
            "strength": "decisive",
            "role": "direct",
            "finding_basis": "direct_result",
        }
    )
    data = data.model_copy(
        update={
            "assessments": (axis,),
            "source_texts": {axis.statement_id: (source,)},
            "relationship_context": {
                "exposure_terms": ("exposure",),
                "outcome_terms": ("disease",),
                "finding_texts": {axis.statement_id: text},
                "disease_onset": True,
            },
        }
    )
    axes, reasons = guarded_axes(data)
    assert axes[0].direction == "neutral" and axes[0].role == "contextual"
    assert code in reasons[axis.statement_id]
    assert data.assessments[0].direction == "opposes_claim"  # Original retained.


def test_incident_disease_trial_endpoint_is_not_a_diagnostic_endpoint():
    judge, pack, response = saved("High blood pressure increases")
    data = qualification_input24(judge, pack, response, "standard")
    axis = data.assessments[0].model_copy(
        update={"direction": "supports_claim", "scope": "aligned"}
    )
    data = data.model_copy(
        update={
            "assessments": (axis,),
            "relationship_context": {
                "exposure_terms": ("treatment",),
                "outcome_terms": ("disease",),
                "finding_texts": {
                    axis.statement_id: "Treated participants had fewer incident disease diagnoses."
                },
                "disease_onset": True,
            },
        }
    )
    axes, reasons = guarded_axes(data)
    assert axes == data.assessments and not reasons


def test_query_plan_preserves_multiword_concept_and_exposure_source():
    _, pack, _ = saved("Blue light")
    plan = plan_pubmed_queries(pack.claim_snapshot)
    assert plan.version == "1.6"
    assert all("smartphone" in q.query.casefold() for q in plan.queries)
    lexical = next(q.query for q in plan.queries if q.family == "lexical")
    assert '"Blue Light"[Title/Abstract]'.casefold() in lexical.casefold()
    assert '"blue"[Title/Abstract]' not in lexical.casefold()
    terms = _atomic_aliases(pack.claim_snapshot, "intervention_or_exposure")
    assert _atomic_coverage(terms, "Methylene blue illuminated by light treats leukemia", 0.5) == 0
    assert _atomic_coverage(terms, "Blue-light exposure", 0.5) == 1


def test_measured_phrase_is_preserved_without_crowding_out_lexical_trial_recall():
    _, pack, _ = saved("High blood pressure increases")
    plan = plan_pubmed_queries(pack.claim_snapshot)
    lexical = next(q.query for q in plan.queries if q.family == "lexical")
    assert '\"High blood pressure\"[Title/Abstract]' in lexical
    assert '\"Hypertension\"[Title/Abstract]' not in lexical
    assert '\"Hypertension\"[MeSH Terms]' in plan.queries[0].query


def test_diagnosis_process_is_not_incident_disease_even_if_model_calls_it_opposition():
    judge, pack, response = saved("High blood pressure causes")
    data = qualification_input24(judge, pack, response, "standard")
    axis = data.assessments[0].model_copy(update={"direction": "opposes_claim"})
    data = data.model_copy(update={"assessments": (axis,),
        "source_texts": {axis.statement_id: ("Exposure enables diagnosis of existing disease.",)},
        "relationship_context": {"exposure_terms": ("exposure",), "outcome_terms": ("disease",),
            "finding_texts": {axis.statement_id: "Exposure enables diagnosis of existing disease."},
            "disease_onset": True}})
    axes, guards = guarded_axes(data)
    assert axes[0].direction == "neutral" and axes[0].scope == "incompatible"
    assert "DISEASE_STAGE_ENDPOINT_MISMATCH" in guards[axis.statement_id]


def test_mortality_word_in_causal_result_is_not_itself_an_ecological_trend():
    judge, pack, response = saved("High blood pressure causes")
    data = qualification_input24(judge, pack, response, "standard")
    axis = data.assessments[0].model_copy(update={"direction": "opposes_claim", "role": "direct"})
    text = "A randomized trial found increased disease incidence and mortality after exposure."
    data = data.model_copy(update={"assessments": (axis,),
        "source_texts": {axis.statement_id: ("Global burden motivates prevention. " + text,)},
        "relationship_context": {"exposure_terms": ("exposure",), "outcome_terms": ("disease",),
            "finding_texts": {axis.statement_id: text}, "disease_onset": True}})
    axes, guards = guarded_axes(data)
    assert axes[0].direction == "opposes_claim" and not guards
    _, old_guards = guarded_axes(data, legacy=True)
    assert "ECOLOGICAL_TREND_IS_CONTEXT" in old_guards[axis.statement_id]


def test_historical_v24_does_not_receive_new_causal_synthesis_flags():
    from test_validated_evidence_position import saved as saved24

    judge, pack, response = saved24("sunscreen")
    assert judge.decision.schema_version == "2.4"
    documents = tuple(d.model_copy(update={"study_design": "review", "abstract_sections": (
        AbstractSection(text="Randomized trials have demonstrated reduced disease incidence."),)})
        for d in pack.documents)
    changed = pack.model_copy(update={"documents": documents})
    data = qualification_input24(judge, changed, response, "standard")
    assert all(f.completed_randomized_result_synthesis is None for finding in data.base.findings
               for f in finding.evidence_design_facts)
    assert data.relationship_context is None
