"""Deterministic study-design and applicability metadata, never a truth score."""

import re

from app.retrieval.models import ClaimSnapshot, PubMedDocument, StudyDesign

_DESIGN_PRIORS: dict[StudyDesign, float] = {
    "meta_analysis": 0.85, "systematic_review": 0.82,
    "randomized_controlled_trial": 0.8, "clinical_trial": 0.72,
    "cohort": 0.67, "case_control": 0.6, "cross_sectional": 0.53,
    "observational": 0.5, "guideline": 0.75, "review": 0.48,
    "case_report": 0.3, "animal_study": 0.25, "in_vitro": 0.2,
    "editorial_or_commentary": 0.2, "other": 0.4, "unknown": 0.4,
}
_PUBTYPE_RULES: tuple[tuple[str, StudyDesign], ...] = (
    ("meta-analysis", "meta_analysis"),
    ("systematic review", "systematic_review"),
    ("randomized controlled trial", "randomized_controlled_trial"),
    ("controlled clinical trial", "clinical_trial"),
    ("clinical trial", "clinical_trial"),
    ("cohort studies", "cohort"),
    ("case-control studies", "case_control"),
    ("cross-sectional studies", "cross_sectional"),
    ("observational study", "observational"),
    ("practice guideline", "guideline"),
    ("guideline", "guideline"),
    ("review", "review"),
    ("case reports", "case_report"),
    ("editorial", "editorial_or_commentary"),
    ("comment", "editorial_or_commentary"),
)
_MESH_RULES: tuple[tuple[str, StudyDesign], ...] = (
    ("meta-analysis as topic", "meta_analysis"),
    ("systematic reviews as topic", "systematic_review"),
    ("randomized controlled trials as topic", "randomized_controlled_trial"),
    ("cohort studies", "cohort"),
    ("case-control studies", "case_control"),
    ("cross-sectional studies", "cross_sectional"),
    ("in vitro techniques", "in_vitro"),
)
_TITLE_RULES: tuple[tuple[str, StudyDesign], ...] = (
    (r"\bmeta-analysis\b", "meta_analysis"),
    (r"\bsystematic review\b", "systematic_review"),
    (r"\brandomi[sz]ed (?:controlled )?trial\b", "randomized_controlled_trial"),
    (r"\bclinical trial\b", "clinical_trial"),
    (r"\bcohort study\b|\bcohort analysis\b", "cohort"),
    (r"\bcase.control study\b", "case_control"),
    (r"\bcross.sectional study\b", "cross_sectional"),
    (r"\bcase report\b", "case_report"),
    (r"\b(?:editorial|commentary)\b", "editorial_or_commentary"),
    (r"\bin vitro\b", "in_vitro"),
)


def classify_study_design(document: PubMedDocument) -> tuple[StudyDesign, str]:
    types = {value.casefold() for value in document.publication_types}
    for label, design in _PUBTYPE_RULES:
        if label in types:
            return design, f"pubmed_publication_type:{label}"
    terms = {value.casefold() for value in document.mesh_terms}
    if "animals" in terms and "humans" not in terms:
        return "animal_study", "pubmed_mesh:animals_without_humans"
    for label, design in _MESH_RULES:
        if label in terms:
            return design, f"pubmed_mesh:{label}"
    for pattern, design in _TITLE_RULES:
        if re.search(pattern, document.title, re.IGNORECASE):
            return design, "title_lexical"
    return "unknown", "unclassified"


def applicability_flags(claim: ClaimSnapshot, document: PubMedDocument) -> tuple[str, ...]:
    population = claim.pico.population.casefold() if claim.pico and claim.pico.population else ""
    terms = {value.casefold() for value in document.mesh_terms}
    title = document.title.casefold()
    flags: list[str] = []
    human_claim = bool(re.search(
        r"\b(humans?|people|patients?|adults?|children|pediatric|pregnan\w*)\b",
        population,
    ))
    if human_claim and document.study_design == "animal_study":
        flags.append("animal_to_human")
    if human_claim and document.study_design == "in_vitro":
        flags.append("in_vitro_to_clinical")
    adult_claim = bool(re.search(r"\badults?\b", population))
    child_claim = bool(re.search(r"\b(children|child|pediatric|infants?)\b", population))
    if adult_claim and "child" in terms and "adult" not in terms:
        flags.append("pediatric_vs_adult")
    if child_claim and "adult" in terms and "child" not in terms:
        flags.append("pediatric_vs_adult")
    if "non-pregnant" in population and "pregnancy" in terms:
        flags.append("pregnancy_population_mismatch")
    if claim.claim_type == "prevention" and re.search(r"\btreatment of\b", title):
        flags.append("prevention_vs_treatment")
    if claim.claim_type == "treatment" and re.search(r"\bprevention of\b", title):
        flags.append("prevention_vs_treatment")
    return tuple(flags)


def annotate_study_quality(claim: ClaimSnapshot, document: PubMedDocument) -> PubMedDocument:
    design, source = classify_study_design(document)
    classified = document.model_copy(update={"study_design": design, "study_design_source": source})
    flags = applicability_flags(claim, classified)
    terms = {term.casefold() for term in document.mesh_terms}
    human_evidence = 1.0 if "humans" in terms else 0.0 if design in {
        "animal_study", "in_vitro"
    } else 0.5
    integrity_multiplier = 0.0 if document.integrity.status == "retracted" else (
        0.5 if document.integrity.status == "expression_of_concern" else 1.0
    )
    applicability_multiplier = 0.8 if flags else 1.0
    base = _DESIGN_PRIORS[design]
    prior = round(base * integrity_multiplier * applicability_multiplier, 4)
    return classified.model_copy(update={
        "quality_prior": prior,
        "quality_factors": {
            "study_design_base": base, "human_evidence": human_evidence,
            "integrity_multiplier": integrity_multiplier,
            "applicability_multiplier": applicability_multiplier,
        },
        "applicability_warnings": flags,
    })
