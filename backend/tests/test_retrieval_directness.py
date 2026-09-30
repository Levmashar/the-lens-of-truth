"""Offline relationship-directness regressions; no PubMed/Crossref calls."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from app.medical.entities import MedicalEntity
from app.pipeline.pico import NormalizedPico
from app.retrieval.evidence_pack import build_evidence_pack, canonical_pack_bytes
from app.retrieval.models import AbstractSection, ClaimSnapshot, EvidencePack, PubMedDocument
from app.retrieval.passages import extract_passages
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import rank_passages

_NOW = datetime(2026, 9, 25, tzinfo=UTC)


def _claim(text: str, exposure: str, outcome: str, kind: str) -> ClaimSnapshot:
    aliases = {
        "Vitamin C": ("D014815", "Ascorbic Acid"),
        "High blood pressure": ("D006973", "Hypertension"),
        "common cold": ("D003139", "Common Cold"),
    }
    entities = tuple(
        MedicalEntity(
            surface_text=value, entity_type=role, mesh_id=aliases[value][0],
            preferred_name=aliases[value][1], match_type="synonym", confidence=0.95,
            terminology_source="mesh", terminology_version="2026",
        )
        for value, role in ((exposure, "intervention_or_exposure"), (outcome, "outcome"))
        if value in aliases
    )
    return ClaimSnapshot(
        claim_id=UUID("11111111-1111-4111-8111-111111111111"),
        raw_text=text, claim_type=kind, entities=entities,
        pico=NormalizedPico(
            original_claim=text, claim_type=kind,
            intervention_or_exposure=exposure, outcome=outcome,
        ),
    )


def _doc(pmid: str, title: str, *sections: tuple[str, str],
         quality: float = 0.4) -> PubMedDocument:
    return PubMedDocument(
        document_id=f"pubmed:{pmid}", pmid=pmid, title=title,
        abstract=" ".join(text for _, text in sections) or None,
        abstract_sections=tuple(AbstractSection(label=label, text=text)
                                for label, text in sections),
        canonical_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        retrieved_at=_NOW, content_sha256=pmid.zfill(64), quality_prior=quality,
        query_ids=("Q1",),
    )


def _pack(claim: ClaimSnapshot, *documents: PubMedDocument) -> EvidencePack:
    passages = tuple(p for doc in documents for p in extract_passages(doc))
    ranked = rank_passages(claim, documents, passages)
    return build_evidence_pack(claim, plan_pubmed_queries(claim), documents, ranked)


def _selected_pmids(pack: EvidencePack) -> list[str]:
    by_id = {passage.evidence_id: passage for passage in pack.passages}
    by_doc = {document.document_id: document.pmid for document in pack.documents}
    return [by_doc[by_id[eid].passage.document_id] for eid in pack.selected_evidence_ids]


def test_vitamin_c_direct_study_outranks_zinc_background_review() -> None:
    claim = _claim("Vitamin C prevents the common cold.", "Vitamin C", "common cold",
                   "prevention")
    direct = _doc("1001", "Vitamin C for preventing the common cold",
                  ("RESULTS", "Vitamin C supplementation reduced common cold incidence."),
                  quality=0.5)
    zinc = _doc("1002", "Zinc for the common cold: a systematic review",
                ("ABSTRACT", "Vitamin C has been studied for preventing common cold. "
                 "This review evaluated zinc and other micronutrients. Micronutrients, "
                 "except vitamin C, may not prevent common cold incidence."),
                quality=0.9)
    pack = _pack(claim, zinc, direct)
    assert _selected_pmids(pack)[0] == "1001"
    zinc_doc = next(doc for doc in pack.documents if doc.pmid == "1002")
    assert zinc_doc.relationship_directness.direction == "incidental"
    assert zinc_doc.relationship_directness.factors["exposure_excluded_from_study"] == 1
    assert any(item.relationship_directness.factors["exposure_excluded_penalty"] > 0
               for item in pack.passages if item.passage.document_id == zinc_doc.document_id)


def test_hypertension_risk_outranks_post_stroke_management() -> None:
    claim = _claim("High blood pressure increases stroke risk.",
                   "High blood pressure", "stroke", "causal")
    direct = _doc("2001", "Hypertension as a risk factor for stroke",
                  ("METHODS", "Baseline hypertension was measured in a prospective cohort."),
                  ("RESULTS", "Hypertension predicted incident stroke."))
    reverse = _doc("2002", "Blood pressure management after stroke",
                   ("RESULTS", "Blood pressure targets were assessed in stroke patients."),
                   quality=0.85)
    post_procedure = _doc(
        "2003", "Blood Pressure Trajectories and Outcomes After Endovascular "
        "Thrombectomy for Acute Ischemic Stroke",
        ("RESULTS", "Higher blood pressure trajectories were associated with poor outcomes "
         "in acute stroke patients."),
    )
    pack = _pack(claim, reverse, post_procedure, direct)
    assert _selected_pmids(pack)[0] == "2001"
    reverse_doc = next(doc for doc in pack.documents if doc.pmid == "2002")
    assert reverse_doc.relationship_directness.direction == "reverse"
    assert "post_outcome_exposure_measurement" in reverse_doc.relationship_directness.reasons
    post_doc = next(doc for doc in pack.documents if doc.pmid == "2003")
    assert post_doc.relationship_directness.direction == "reverse"
    assert len(pack.passages) == sum(len(extract_passages(doc))
                                    for doc in (direct, reverse, post_procedure))


def test_management_of_existing_disease_does_not_outrank_incidence_study() -> None:
    claim = _claim("High blood pressure causes stroke.", "High blood pressure", "stroke",
                   "causal")
    risk = _doc("2011", "High blood pressure and incident stroke in adults",
                ("RESULTS", "High blood pressure predicted incident stroke."))
    treatment = _doc(
        "2012", "Intensive blood-pressure reduction in hyperacute stroke",
        ("METHODS", "Patients with acute stroke received blood-pressure reduction."),
        quality=0.8,
    )
    pack = _pack(claim, treatment, risk)
    by_pmid = {document.pmid: document for document in pack.documents}
    assert by_pmid["2012"].relationship_directness.direction == "reverse"
    assert _selected_pmids(pack)[0] == "2011"
    assert all(item.selection_priority_score <= 1 for item in pack.passages)


def test_risk_of_disease_demotes_progression_and_mortality_only_endpoints() -> None:
    claim = _claim("Smoking increases the risk of lung cancer.", "Smoking", "lung cancer",
                   "causal")
    direct = _doc("3011", "Smoking and lung cancer incidence in a cohort",
                  ("RESULTS", "Smoking predicted incident lung cancer cases."))
    progression = _doc("3012", "Smoking and lung cancer progression",
                       ("RESULTS", "Smoking influenced lung cancer cell progression."))
    mortality = _doc("3013", "Predicting lung cancer deaths from smoking prevalence",
                     ("RESULTS", "Smoking prevalence predicted lung cancer deaths."))
    pack = _pack(claim, mortality, progression, direct)
    by_pmid = {document.pmid: document for document in pack.documents}
    assert _selected_pmids(pack)[0] == "3011"
    assert by_pmid["3011"].endpoint_directness.score > (
        by_pmid["3012"].endpoint_directness.score
    )
    assert by_pmid["3011"].endpoint_directness.score > (
        by_pmid["3013"].endpoint_directness.score
    )
    assert "post_disease_endpoint" in by_pmid["3012"].endpoint_directness.warnings
    assert "3012" not in _selected_pmids(pack)
    assert "3013" not in _selected_pmids(pack)
    assert EvidencePack.model_validate_json(pack.model_dump_json()) == pack


def test_post_outcome_rule_uses_pico_outcome_not_disease_name() -> None:
    claim = _claim("Aspirin increases heart attack risk.", "Aspirin", "heart attack",
                   "causal")
    document = _doc("2051", "Aspirin management after heart attack",
                    ("RESULTS", "Aspirin treatment was assessed in heart attack survivors."))
    pack = _pack(claim, document)
    assert pack.documents[0].relationship_directness.direction == "reverse"
    assert "post_outcome_exposure_measurement" in (
        pack.documents[0].relationship_directness.reasons
    )


def test_smoking_risk_outranks_screening_and_never_smokers() -> None:
    claim = _claim("Smoking increases the risk of lung cancer.", "Smoking", "lung cancer",
                   "causal")
    direct = _doc("3001", "Smoking and lung cancer incidence in a cohort",
                  ("RESULTS", "Smoking exposure predicted incident lung cancer."))
    screening = _doc("3002", "Lung cancer screening and smoking cessation",
                     ("RESULTS", "Screening increased smoking cessation rates."), quality=0.8)
    cessation_context = _doc(
        "3004", "Electronic cigarette use after smoking cessation and lung cancer risk",
        ("RESULTS", "Electronic cigarette use after smoking cessation was associated "
         "with lung cancer incidence."),
    )
    never = _doc("3003", "Lung cancer in never-smoking women",
                 ("METHODS", "We studied lung cancer in never-smoking women."),
                 ("BACKGROUND", "Smoking is a known risk factor for lung cancer."),
                 quality=0.85)
    pack = _pack(claim, never, screening, cessation_context, direct)
    assert _selected_pmids(pack)[0] == "3001"
    by_pmid = {doc.pmid: doc for doc in pack.documents}
    assert by_pmid["3002"].relationship_directness.direction == "incidental"
    assert by_pmid["3004"].relationship_directness.direction == "incidental"
    assert "exposure_excluded_population" in by_pmid["3003"].relationship_directness.warnings
    assert len(set(_selected_pmids(pack))) == len(pack.selected_evidence_ids)
    assert EvidencePack.model_validate_json(pack.model_dump_json()) == pack


def test_background_only_and_covariate_only_are_not_direct_exposure_studies() -> None:
    claim = _claim("Smoking increases the risk of lung cancer.", "Smoking", "lung cancer",
                   "causal")
    background = _doc("3101", "Depression and cancer incidence",
                      ("BACKGROUND", "Smoking and lung cancer are common public health "
                       "concerns."),
                      ("RESULTS", "Depression predicted cancer incidence."))
    covariate = _doc("3102", "Depression, anxiety, and the risk of cancer",
                     ("RESULTS", "Depression was associated with lung cancer incidence "
                      "after adjustment for smoking, alcohol use and age."))
    pack = _pack(claim, background, covariate)
    by_pmid = {doc.pmid: doc for doc in pack.documents}
    assert by_pmid["3101"].relationship_directness.factors["exposure_only_background"] == 1
    assert by_pmid["3101"].relationship_directness.factors["outcome_only_background"] == 1
    assert by_pmid["3101"].relationship_directness.direction == "incidental"
    assert by_pmid["3102"].relationship_directness.direction == "incidental"
    assert (by_pmid["3102"].relationship_directness.factors[
        "exposure_used_as_adjustment_covariate"] == 1)
    assert len(pack.passages) == 5


def test_incidental_outcome_in_background_is_exposed() -> None:
    claim = _claim("Smoking increases the risk of lung cancer.", "Smoking", "lung cancer",
                   "causal")
    document = _doc("3151", "Smoking and cardiovascular outcomes",
                    ("BACKGROUND", "Lung cancer is another concern."),
                    ("RESULTS", "Smoking predicted cardiovascular events."))
    pack = _pack(claim, document)
    assert pack.documents[0].relationship_directness.direction == "incidental"
    assert pack.documents[0].relationship_directness.factors["outcome_only_background"] == 1
    background = next(p for p in pack.passages if p.passage.section == "BACKGROUND")
    assert background.relationship_directness.factors["incidental_mention_penalty"] > 0


def test_adjacent_sentences_do_not_imply_aligned_direction() -> None:
    claim = _claim("Smoking increases the risk of lung cancer.", "Smoking", "lung cancer",
                   "causal")
    document = _doc("3201", "Population survey",
                    ("ABSTRACT", "Smoking habits were recorded. Lung cancer cases were "
                     "also recorded."))
    pack = _pack(claim, document)
    abstract = next(item for item in pack.passages if item.passage.section == "ABSTRACT")
    assert abstract.relationship_directness.factors["both_in_adjacent_sentences"] == 1
    assert abstract.relationship_directness.factors["both_in_same_sentence"] == 0
    assert pack.documents[0].relationship_directness.direction == "unknown"


def test_section_proximity_and_unknown_direction_are_explicit() -> None:
    claim = _claim("Smoking increases the risk of lung cancer.", "Smoking", "lung cancer",
                   "causal")
    same = _doc("4001", "Population study",
                ("RESULTS", "Smoking was linked to lung cancer incidence."))
    separated = _doc("4002", "Population study",
                     ("METHODS", "Smoking was measured."),
                     ("RESULTS", "Lung cancer was observed."))
    pack = _pack(claim, same, separated)
    results = [p for p in pack.passages if p.passage.section == "RESULTS"]
    same_result = next(p for p in results if p.passage.document_id == "pubmed:4001")
    separated_result = next(p for p in results if p.passage.document_id == "pubmed:4002")
    assert same_result.relationship_directness.factors["both_in_same_sentence"] == 1
    assert separated_result.relationship_directness.factors["both_in_same_sentence"] == 0
    assert (same_result.relationship_directness.score >
            separated_result.relationship_directness.score)
    separated_doc = next(doc for doc in pack.documents if doc.pmid == "4002")
    assert separated_doc.relationship_directness.direction == "unknown"


def test_result_passage_outweighs_background_and_contradiction_stays_direct() -> None:
    claim = _claim("Smoking increases the risk of lung cancer.", "Smoking", "lung cancer",
                   "causal")
    doc = _doc("5001", "Smoking and lung cancer risk",
               ("BACKGROUND", "Smoking and lung cancer risk have been debated."),
               ("RESULTS", "Smoking was not associated with increased lung cancer risk."))
    pack = _pack(claim, doc)
    by_section = {p.passage.section: p for p in pack.passages}
    assert by_section["RESULTS"].relationship_directness.score > (
        by_section["BACKGROUND"].relationship_directness.score
    )
    assert pack.documents[0].relationship_directness.direction == "aligned"
    assert _selected_pmids(pack) == ["5001"]


def test_directness_metadata_and_selection_change_hash_deterministically() -> None:
    claim = _claim("Smoking increases the risk of lung cancer.", "Smoking", "lung cancer",
                   "causal")
    direct = _doc("6001", "Smoking and lung cancer risk",
                  ("RESULTS", "Smoking predicted lung cancer incidence."))
    original = _pack(claim, direct)
    assert original.snapshot_hash == _pack(claim, direct).snapshot_hash
    changed = _doc("6001", "Smoking and lung cancer risk",
                   ("RESULTS", "Smoking and lung cancer were recorded."))
    revised = _pack(claim, changed)
    assert revised.snapshot_hash != original.snapshot_hash
    assert (original.documents[0].relationship_directness !=
            revised.documents[0].relationship_directness)
    assert len(original.passages) == len(revised.passages)
    original_bytes = canonical_pack_bytes(
        claim, original.query_plan, original.documents, original.passages,
        original.selected_evidence_ids,
    )
    changed_detail = original.passages[0].relationship_directness.model_copy(update={
        "score": 0.0,
    })
    changed_passage = original.passages[0].model_copy(update={
        "relationship_directness": changed_detail,
    })
    metadata_only = canonical_pack_bytes(
        claim, original.query_plan, original.documents,
        (changed_passage, *original.passages[1:]), original.selected_evidence_ids,
    )
    assert hashlib.sha256(metadata_only).hexdigest() != hashlib.sha256(
        original_bytes
    ).hexdigest()


def test_mmr_vaccination_cohort_beats_social_and_handout_candidates() -> None:
    claim = _claim("MMR vaccine causes autism.", "MMR vaccine", "autism", "causal")
    claim = claim.model_copy(update={"entities": (MedicalEntity(
        surface_text="MMR vaccine", entity_type="intervention_or_exposure",
        mesh_id="D022542", preferred_name="Measles-Mumps-Rubella Vaccine",
        match_type="synonym", confidence=0.95,
        terminology_source="mesh", terminology_version="2026",
    ),)})
    cohort = _doc(
        "30831578", "Measles, Mumps, Rubella Vaccination and Autism: "
        "A Nationwide Cohort Study.",
        ("RESULTS", "Comparing MMR-vaccinated with MMR-unvaccinated children "
         "yielded an autism hazard ratio of 0.93."),
        ("CONCLUSION", "MMR vaccination was not associated with increased autism risk."),
        quality=0.67,
    )
    social = _doc(
        "32057491", "Confirmatory bias in health decisions: Evidence from "
        "the MMR-autism controversy.",
        ("ABSTRACT", "Parents discussed MMR vaccine and autism risk."),
    )
    handout = _doc(
        "30831599", "The MMR Vaccine Is Not Associated With Risk for Autism.",
    ).model_copy(update={"publication_types": ("Patient Education Handout",)})
    pack = _pack(claim, social, handout, cohort)
    assert _selected_pmids(pack) == ["30831578"]
    by_pmid = {document.pmid: document for document in pack.documents}
    assert by_pmid["30831578"].relationship_directness.direction == "aligned"
    assert by_pmid["32057491"].relationship_directness.direction == "incidental"
    assert len(pack.documents) == 3
    reasons = {
        next(doc.pmid for doc in pack.documents
             if doc.document_id == item.passage.document_id): item.selection_reason
        for item in pack.passages if not item.selected_for_judging
    }
    assert reasons["30831599"] == "non_evidence_publication_excluded"


def test_direct_smoking_review_beats_genetic_modifier_question() -> None:
    claim = _claim("Smoking increases the risk of lung cancer.", "Smoking", "lung cancer",
                   "causal")
    direct = _doc(
        "12362269", "Molecular epidemiology of smoking and lung cancer.",
        ("ABSTRACT", "Tobacco smoking causes lung cancer and increases its incidence."),
        quality=0.48,
    )
    genetics = _doc(
        "39366959", "Multi-ancestry GWAS meta-analyses of lung cancer reveal "
        "susceptibility loci and elucidate smoking-independent genetic risk.",
        ("ABSTRACT", "Genetic risk of lung cancer was distinguished from smoking "
         "behavioral susceptibility."), quality=0.85,
    )
    interaction = _doc(
        "38117513", "CYP2A6 Activity and Cigarette Consumption Interact in "
        "Smoking-Related Lung Cancer Susceptibility.",
        ("ABSTRACT", "Cigarette smoking causes lung cancer. Genetic variants "
         "modified lung cancer susceptibility in smokers."),
    )
    pack = _pack(claim, genetics, interaction, direct)
    assert _selected_pmids(pack)[0] == "12362269"
    by_pmid = {document.pmid: document for document in pack.documents}
    assert by_pmid["39366959"].relationship_directness.direction == "incidental"
    selected = {item.evidence_id for item in pack.passages if item.selected_for_judging}
    assert not any(item.evidence_id in selected and item.passage.document_id ==
                   "pubmed:39366959" for item in pack.passages)
    assert len(pack.documents) == 3


def test_two_direct_titles_prevent_generic_outcome_reviews_from_padding_pack() -> None:
    claim = _claim("Smoking increases the risk of lung cancer.", "Smoking", "lung cancer",
                   "causal")
    first = _doc("7101", "Smoking and lung cancer incidence in a cohort",
                 ("RESULTS", "Smoking increased incident lung cancer risk."))
    second = _doc("7102", "Smoking and lung cancer risk in adults",
                  ("RESULTS", "Smoking was associated with lung cancer incidence."))
    background = _doc("7103", "The epidemiology of lung cancer",
                      ("ABSTRACT", "Smoking is associated with lung cancer incidence."),
                      quality=0.9)
    pack = _pack(claim, background, first, second)
    assert set(_selected_pmids(pack)) == {"7101", "7102"}
    assert len(pack.documents) == 3
    assert any(item.selection_reason == "direct_title_evidence_available"
               for item in pack.passages if item.passage.document_id == "pubmed:7103")
    assert EvidencePack.model_validate_json(pack.model_dump_json()) == pack


def test_title_only_paper_does_not_displace_full_direct_abstract() -> None:
    claim = _claim("Smoking increases the risk of lung cancer.", "Smoking", "lung cancer",
                   "causal")
    full = _doc("7201", "Smoking and lung cancer incidence in a cohort",
                ("RESULTS", "Smoking increased incident lung cancer risk."))
    title_only = _doc("7202", "Smoking and lung cancer")
    pack = _pack(claim, title_only, full)
    assert _selected_pmids(pack) == ["7201"]
    assert len(pack.documents) == 2
    assert any(item.selection_reason == "title_only_when_abstract_available"
               for item in pack.passages if item.passage.document_id == "pubmed:7202")
    assert EvidencePack.model_validate_json(pack.model_dump_json()) == pack
