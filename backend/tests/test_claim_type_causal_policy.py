"""Etiology/transmission evidence versus intervention and unsupported opinion."""

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_reliability_slice3 import claim, source

from app.adapters.authoritative import (
    freeze_html,
    update_date,
)
from app.judging.models import JudgeRun
from app.pipeline.pico import NormalizedPico
from app.retrieval.causal_policy import POLICY, assessment_facts
from app.retrieval.evidence_pack import build_evidence_pack
from app.retrieval.models import EvidencePack, PubMedDocument
from app.retrieval.passages import extract_passages
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import rank_passages
from app.retrieval.sufficiency import (
    EvidenceDesignFact,
    design_eligible,
    design_fact,
    question_category,
)
from app.validation.audit25 import audit_matches25
from app.validation.axes import AxesQualifierInput, EvidenceClaimAssessment
from app.validation.joint23 import JointResponse23
from app.validation.joint24 import qualification_input24
from app.validation.models import JudgeValidationRun
from app.validation.position import derive_position
from app.validation.qualification import ConclusionQualifierInput, FindingQualificationInput
from app.validation.relationship_guards import RelationshipContext

FIXTURES = Path(__file__).with_name("fixtures")
ROWS = json.loads(gzip.decompress((FIXTURES / "causal_policy_before.json.gz").read_bytes()))
AUTHORITY = tuple(PubMedDocument.model_validate(d) for d in json.loads(gzip.decompress(
    (FIXTURES / "causal_policy_authority.json.gz").read_bytes())))


def fact(**changes):
    return EvidenceDesignFact.model_validate({
        "document_id": "authoritative:fixture", "analysis_design": "unknown",
        "exposure_assignment": "unknown", "source_kind": "authoritative_public_health",
        "document_purpose": "causal_assessment", "role": "direct", "integrity": "valid",
        "currency": "current", "independence_group": "fixture",
        "causal_assessment_text": "Factor X causes disease Y.",
        "causal_evidence_components": ("reviewed_assessment",), **changes})


@pytest.mark.parametrize("row", ROWS, ids=lambda r: str(r["number"]))
def test_all_previous_live_audits_remain_exact_and_controls_preserve_positions(row):
    pack = EvidencePack.model_validate(row["pack"])
    for vd in row["validations"]:
        judge = JudgeRun.model_validate_json(json.dumps(next(j for j in row["judges"]
                                            if j["judge_run_id"] == vd["judge_run_id"])))
        audit = JudgeValidationRun.model_validate_json(json.dumps(vd))
        assert audit_matches25(judge, audit, pack, "standard")
        response = JointResponse23.model_validate_json(json.dumps(
            audit.result.relation_validation["joint_response"]))
        inputs = qualification_input24(judge, pack, response, "standard")
        if row["number"] in {6, 109, 101, 102}:
            assert derive_position(inputs).validated_evidence_position \
                == audit.result.validated_evidence_position
        if row["number"] == 3:
            assert inputs.base.question_category == "etiologic_exposure_causality"
        if row["number"] == 15:
            assert inputs.base.question_category == "disease_transmission"


@pytest.mark.parametrize("text,exposure,kind", [
    ("A virus causes a disease.", "A virus", "etiologic_exposure_causality"),
    ("Infection is transmitted by water.", "water", "disease_transmission"),
    ("Lowering high blood pressure reduces stroke risk.", "Lowering high blood pressure",
     "intervention_causality"),
    ("Medication reduces infection transmission.", "Medication", "intervention_causality"),
])
def test_taxonomy_uses_question_semantics_and_ontology_not_disease_ids(text, exposure, kind):
    c = claim().model_copy(update={"raw_text": text, "normalized_text": None,
        "pico": NormalizedPico(original_claim=text, claim_type="causal",
                               intervention_or_exposure=exposure, outcome="a disease"),
        "entities": ()})
    if "virus causes" in text:
        from app.medical.entities import MedicalEntity

        c = c.model_copy(update={"entities": (MedicalEntity(
            surface_text="virus", entity_type="intervention_or_exposure", mesh_id="D000001",
            confidence=.95, match_type="exact", tree_numbers=("B04.000",)),)})
    assert question_category(c, causal_policy=True) == kind
    if kind == "etiologic_exposure_causality":
        assert question_category(c) == "intervention_causality"  # Historical taxonomy.


@pytest.mark.parametrize("change", [
    {"document_purpose": "fact_sheet"}, {"document_purpose": "public_health_guidance"},
    {"document_purpose": "press_release"}, {"currency": "unknown"}, {"currency": "stale"},
    {"role": "contextual"}, {"integrity": "retracted"}, {"causal_assessment_text": None},
    {"causal_evidence_components": ()},
])
def test_publisher_prestige_cannot_replace_an_explicit_current_valid_assessment(change):
    assert not design_eligible("etiologic_exposure_causality", fact(**change), policy=POLICY)


@pytest.mark.parametrize("kind", ["treatment", "prevention", "intervention_causality"])
def test_etiologic_policy_preserves_existing_intervention_rules(kind):
    assert not design_eligible(kind, fact(), policy=POLICY)
    observational = fact(source_kind="pubmed", analysis_design="meta_analysis",
                         exposure_assignment="synthesized", synthesis_randomized_trials=None)
    assert (design_eligible(kind, observational, policy=POLICY)
            == design_eligible(kind, observational))
    cohort = observational.model_copy(update={"analysis_design": "prospective_cohort",
                                              "exposure_assignment": "observed"})
    assert not design_eligible(kind, cohort, policy=POLICY)
    assert design_eligible(kind, observational.model_copy(
        update={"synthesis_randomized_trials": True}), policy=POLICY)
    assert design_eligible(kind, fact(source_kind="pubmed",
        analysis_design="randomized_intervention", exposure_assignment="randomized"), policy=POLICY)


def test_primary_epidemiology_needs_independent_convergence_and_temporality():
    cohort = fact(source_kind="pubmed", analysis_design="prospective_cohort",
                  exposure_assignment="observed", causal_evidence_components=(
                      "primary_epidemiology", "epidemiology", "temporality"))
    case_control = cohort.model_copy(update={"document_id": "pubmed:second",
        "analysis_design": "case_control", "independence_group": "independent",
        "causal_evidence_components": ("primary_epidemiology", "epidemiology")})
    assert not design_eligible("etiologic_exposure_causality", cohort, policy=POLICY)
    assert not design_eligible("etiologic_exposure_causality", cohort, policy=POLICY,
                               peers=(cohort,))
    assert design_eligible("etiologic_exposure_causality", cohort, policy=POLICY,
                           peers=(case_control,))
    assert not design_eligible("treatment", cohort, policy=POLICY, peers=(case_control,))
    assert not design_eligible("etiologic_exposure_causality", cohort.model_copy(
        update={"causal_evidence_components": ("epidemiology",)}), policy=POLICY,
        peers=(case_control,))


def test_validated_causal_convergence_survives_incidental_association_wording():
    statements = {"S1": "Factor X causes disease Y in the prospective analysis.",
                  "S2": "Factor X causes disease Y in the case-control analysis."}
    facts = tuple(fact(document_id="pubmed:"+s, source_kind="pubmed",
                       analysis_design="prospective_cohort" if s == "S1" else "case_control",
                       exposure_assignment="observed", independence_group=s,
                       causal_evidence_components=("epidemiology", "temporality"))
                  for s in statements)
    findings = tuple(FindingQualificationInput(statement_id=s, study_designs=("cohort",),
        deterministic_scopes=("aligned",), deterministic_relations=("weaker_than_claim",),
        integrity_statuses=("valid",), evidence_design_facts=(f,))
        for s, f in zip(statements, facts, strict=True))
    axes = tuple(EvidenceClaimAssessment(statement_id=s, direction="supports_claim",
        scope="aligned", strength="strong", role="direct", scope_basis="same_question",
        finding_basis="causal_assessment", reason="Source conclusion and empirical design.")
        for s in statements)
    inputs = AxesQualifierInput(base=ConclusionQualifierInput(proposed_label=None,
        claim_type="causal", risk_class="standard", findings=findings, relations=(),
        based_on_statement_ids=tuple(statements), evidence_policy=POLICY,
        question_category="etiologic_exposure_causality"), assessments=axes,
        exact_claim="Factor X causes disease Y.", comparator=None,
        source_texts={s: (t,) for s,t in statements.items()},
        relationship_context=RelationshipContext(exposure_terms=("Factor X",),
            outcome_terms=("disease Y",), finding_texts=statements,
            disease_onset=True).model_dump(mode="json"))
    position = derive_position(inputs)
    assert position.validated_evidence_position == "supported"
    assert position.finding_relation_overrides == {"S1": ("aligned",), "S2": ("aligned",)}
    alone = inputs.model_copy(update={"base": inputs.base.model_copy(update={
        "findings": findings[:1], "based_on_statement_ids": ("S1",)}), "assessments": axes[:1]})
    assert derive_position(alone).validated_evidence_position == "not_enough_evidence"
    disclaimer = findings[0].model_copy(update={"evidence_design_facts": (
        facts[0].model_copy(update={"causal_evidence_components": ("causality_disclaimed",)}),)})
    blocked = inputs.model_copy(update={"base": inputs.base.model_copy(
        update={"findings": (disclaimer, findings[1])})})
    assert derive_position(blocked).validated_evidence_position == "not_enough_evidence"


@pytest.mark.parametrize("statement", [
    "Smoking may cause lung cancer.", "I believe smoking causes lung cancer.",
    "There is no evidence that smoking causes lung cancer.",
    "Smoking is associated with lung cancer.", "Smoking causes another disease.",
])
def test_speculation_absence_association_and_wrong_endpoint_are_not_causal_assessments(statement):
    d = freeze_html(source(), '<main id="evidence"><p>'+statement+'</p></main>'
                    '<time datetime="2025-04-01">date</time>',
                    now=datetime(2026, 10, 1, tzinfo=UTC))
    assert not assessment_facts(d, claim(), "Smoking causes lung cancer.", (statement,))


@pytest.mark.parametrize("number", [3, 15])
def test_real_frozen_approved_assessments_are_retrievable_and_finding_bound(number):
    c = EvidencePack.model_validate(next(r for r in ROWS if r["number"] == number)["pack"])
    docs = tuple(d for d in AUTHORITY if (number == 3) == (d.authoritative.organization == "NCI"))
    passages = tuple(p for d in docs for p in extract_passages(d))
    pack = build_evidence_pack(c.claim_snapshot, plan_pubmed_queries(c.claim_snapshot), docs,
        rank_passages(c.claim_snapshot, docs, passages), pack_version="1.5")
    eligible = []
    for d in pack.documents:
        for p in pack.passages:
            if p.selected_for_judging and p.passage.document_id == d.document_id:
                f = design_fact(d).model_copy(update=assessment_facts(d, c.claim_snapshot,
                    c.claim_snapshot.standalone_text, (p.passage.text,)))
                eligible.append(design_eligible(question_category(c.claim_snapshot,
                    causal_policy=True), f, policy=POLICY))
    assert any(eligible)
    assert plan_pubmed_queries(c.claim_snapshot).version == "1.6"
    assert any('"Cohort Studies"[MeSH Terms]' in q.query
               for q in plan_pubmed_queries(c.claim_snapshot).queries)


def test_visible_document_abbreviated_date_is_parsed_but_comment_footer_is_not():
    assert str(update_date('<p>Content last updated Jun 14, 2022</p>')) == "2022-06-14"
    assert update_date('<!-- Updated: Jun 14, 2022 --><footer>Updated: July 4, 2023</footer>') \
        is None


def test_transmission_list_keeps_the_negative_introduction_exactly():
    s = source().model_copy(update={"retrieval_method": "html_lists"})
    d = freeze_html(s, '<main id="evidence"><p>Virus Q is not transmitted by</p>'
        '<ul><li>Contact with surfaces.</li><li>Some insect bites.</li></ul></main>'
        '<time datetime="2025-04-01">date</time>', now=datetime(2026, 10, 1, tzinfo=UTC))
    assert d.abstract_sections[0].text == (
        "Virus Q is not transmitted by Contact with surfaces. Some insect bites.")
    assert d.authoritative.extraction_version == "approved-html-1.1"
