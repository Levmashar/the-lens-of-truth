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
from app.retrieval.study_quality import annotate_study_quality

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


def test_absolute_soy_muscle_claim_excludes_active_comparator_only_questions() -> None:
    claim = _claim("Soy use lowers muscle gain.", "soy use", "muscle gain", "causal")
    soy_whey = _doc(
        "32486007", "No Significant Differences in Muscle Growth When Consuming "
        "Soy and Whey Protein Supplements: A Randomized Trial",
        ("RESULTS", "Soy and whey protein groups had similar muscle gain."),
    )
    soy_animal = _doc(
        "29722584", "No Difference Between the Effects of Soy Protein Versus "
        "Animal Protein on Gains in Muscle Mass",
        ("RESULTS", "Soy protein compared with animal protein did not differ "
         "in muscle gain."),
    )
    direct = _doc(
        "8001", "Soy intake frequency and muscle gain in adults",
        ("RESULTS", "Greater soy intake was associated with muscle gain."),
    )
    pack = _pack(claim, soy_whey, soy_animal, direct)
    assert _selected_pmids(pack) == ["8001"]
    assert {item.selection_reason for item in pack.passages
            if item.passage.document_id in {"pubmed:32486007", "pubmed:29722584"}} == {
                "unstated_active_comparator_excluded",
            }
    assert len(pack.documents) == 3
    assert EvidencePack.model_validate_json(pack.model_dump_json()) == pack


def test_active_comparator_guard_preserves_null_selection_when_only_relative_papers() -> None:
    claim = _claim("Soy use lowers muscle gain.", "soy use", "muscle gain", "causal")
    relative = _doc(
        "8002", "Soy protein versus whey protein for muscle gain",
        ("RESULTS", "Soy and whey protein yielded similar muscle gain."),
    )
    pack = _pack(claim, relative)
    assert pack.selected_evidence_ids == ()
    assert len(pack.passages) == 2
    assert all(item.selection_reason == "unstated_active_comparator_excluded"
               for item in pack.passages)


def test_active_comparator_guard_allows_no_exposure_control_and_asserted_comparator() -> None:
    absolute = _claim("Soy use lowers muscle gain.", "soy use", "muscle gain", "causal")
    placebo = _doc(
        "8003", "Soy protein versus placebo for muscle gain",
        ("RESULTS", "Soy protein increased muscle gain versus placebo."),
    )
    assert _selected_pmids(_pack(absolute, placebo)) == ["8003"]

    relative = _claim("Soy use versus whey protein lowers muscle gain.",
                      "soy use", "muscle gain", "causal")
    relative = relative.model_copy(update={
        "pico": relative.pico.model_copy(update={"comparator": "whey protein"})
        if relative.pico else None,
    })
    whey = _doc(
        "8004", "Soy protein versus whey protein for muscle gain",
        ("RESULTS", "Soy protein yielded less muscle gain than whey protein."),
    )
    assert _selected_pmids(_pack(relative, whey)) == ["8004"]


def test_active_comparator_guard_allows_nonusers_no_soy_and_dose_contrasts() -> None:
    claim = _claim("Soy use lowers muscle gain.", "soy use", "muscle gain", "causal")
    nonusers = _doc(
        "8011", "Soy users versus nonusers and muscle gain",
        ("RESULTS", "Soy users and nonusers differed in muscle gain."),
    )
    no_soy = _doc(
        "8012", "Soy versus no soy and muscle gain",
        ("RESULTS", "Soy exposure and no soy exposure differed in muscle gain."),
    )
    dose = _doc(
        "8013", "Comparison of soy doses for muscle gain",
        ("RESULTS", "Different soy doses were associated with muscle gain."),
    )
    pack = _pack(claim, nonusers, no_soy, dose)
    assert set(_selected_pmids(pack)) == {"8011", "8012", "8013"}


def _soy_muscle_claim() -> ClaimSnapshot:
    claim = _claim("Soy use lowers muscle gain.", "soy use", "muscle gain", "causal")
    return claim.model_copy(update={"entities": (MedicalEntity(
        surface_text="muscle", entity_type="outcome", mesh_id="D009132",
        preferred_name="Muscles", match_type="synonym", confidence=0.95,
        terminology_source="mesh", terminology_version="2026",
    ),)})


def test_muscle_soreness_and_protein_synthesis_do_not_substitute_for_gain() -> None:
    claim = _soy_muscle_claim()
    soreness = _doc(
        "41432641", "Effects of Soy Pretzel Consumption on Blood Biomarkers "
        "and Muscle Soreness After Intense Resistance Exercise",
        ("ABSTRACT", "Soy pretzel consumption was studied for blood biomarkers, "
         "serum testosterone and muscle soreness. Muscle soreness was measured "
         "after intense exercise, not long-term muscle size."),
    )
    synthesis = _doc(
        "8014", "Soy protein and muscle protein synthesis after exercise",
        ("RESULTS", "Soy protein affected muscle protein synthesis after exercise."),
    )
    direct = _doc(
        "8015", "Soy use and muscle growth during resistance training",
        ("RESULTS", "Soy users showed measurable muscle gains during the trial."),
    )
    pack = _pack(claim, soreness, synthesis, direct)
    assert _selected_pmids(pack) == ["8015"]
    by_pmid = {document.pmid: document for document in pack.documents}
    for pmid in ("41432641", "8014"):
        detail = by_pmid[pmid].endpoint_directness
        assert detail.factors["specific_size_endpoint_required"] == 1
        assert detail.factors["specific_size_endpoint_present"] == 0
        assert "specific_size_endpoint_absent" in detail.warnings
        assert {item.selection_reason for item in pack.passages
                if item.passage.document_id == f"pubmed:{pmid}"} == {
                    "specific_outcome_endpoint_absent_excluded",
                }
    assert by_pmid["8015"].endpoint_directness.factors[
        "specific_size_endpoint_present"] == 1
    assert len(pack.documents) == 3


def test_muscle_mass_change_is_direct_gain_endpoint_but_mass_mention_is_not() -> None:
    claim = _soy_muscle_claim()
    changed_mass = _doc(
        "8016", "Soy use and muscle mass after resistance training",
        ("RESULTS", "Soy use increased muscle mass during resistance training."),
    )
    unchanged_context = _doc(
        "8017", "Soy use and muscle mass biomarkers",
        ("RESULTS", "Soy use changed blood biomarkers, while muscle mass was not "
         "measured."),
    )
    strength = _doc(
        "8018", "Soy use and muscle soreness after exercise",
        ("RESULTS", "Soy use affected muscle soreness and gains in strength."),
    )
    pack = _pack(claim, changed_mass, unchanged_context, strength)
    assert _selected_pmids(pack) == ["8016"]


def test_numbered_soy_arm_women_only_is_not_selected_for_male_claim() -> None:
    base = _soy_muscle_claim()
    claim = base.model_copy(update={
        "pico": base.pico.model_copy(update={"population": "men"}) if base.pico else None,
    })
    mixed_trial = _doc(
        "34358827", "Supplement-based nutritional strategies to tackle frailty: "
        "A multifactorial, double-blind, randomized placebo-controlled trial.",
        ("METHODS", "Four integrated sub-investigations were conducted to compare: "
         "1) leucine vs. placebo; 2) whey vs. soy vs. placebo; "
         "3) creatine vs. whey vs. placebo; 4) women vs. men in response to whey. "
         "Sub-investigations 1 to 3 were conducted in women, only. "
         "The whole study included 154 women and 46 men."),
        ("RESULTS", "Supplementation with whey and soy failed to enhance "
         "resistance-training effects. Resistance exercise increased muscle mass."),
    )
    classified = annotate_study_quality(claim, mixed_trial)
    assert "female_exposure_arm_only_vs_male_claim" in classified.applicability_warnings
    assert "female_only_vs_male_claim" not in classified.applicability_warnings
    pack = _pack(claim, classified)
    assert pack.selected_evidence_ids == ()
    assert all(item.selection_reason == "exposure_arm_population_mismatch_excluded"
               for item in pack.passages)
    assert len(pack.documents) == 1


def test_numbered_soy_arm_matching_population_or_mixed_does_not_trigger_guard() -> None:
    base = _soy_muscle_claim()
    claim = base.model_copy(update={
        "pico": base.pico.model_copy(update={"population": "men"}) if base.pico else None,
    })
    male_arm = _doc(
        "8019", "Soy supplements and muscle mass in a multifactorial trial",
        ("METHODS", "Two sub-studies were conducted to compare: "
         "1) whey vs. placebo; 2) soy vs. placebo. "
         "Sub-studies 1 to 1 were conducted in women, only. "
         "Sub-study 2 was conducted in men, only."),
        ("RESULTS", "Soy supplementation increased muscle mass in men."),
    )
    unassigned = _doc(
        "8020", "Soy supplements and muscle mass in men and women",
        ("METHODS", "Men and women were studied across several intervention arms."),
        ("RESULTS", "Soy supplementation increased muscle mass."),
    )
    classified = tuple(annotate_study_quality(claim, item)
                       for item in (male_arm, unassigned))
    assert all("female_exposure_arm_only_vs_male_claim" not in item.applicability_warnings
               for item in classified)
    pack = _pack(claim, *classified)
    assert set(_selected_pmids(pack)) == {"8019", "8020"}
