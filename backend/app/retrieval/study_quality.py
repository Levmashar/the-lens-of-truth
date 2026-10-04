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
_EXPLICIT_ANIMAL = re.compile(
    r"\b(?:mice|mouse|rats?|pigs?|swine|porcine|ducks?|broilers?|"
    r"chickens?|crabs?|rodents?|rabbits?)\b", re.I,
)
_EXPLICIT_HUMAN = re.compile(
    r"\b(?:humans?|people|patients?|adults?|children|men|women|boys|girls)\b", re.I,
)
_NUMBERED_SUBSTUDY_INTRO = re.compile(
    r"\bsub[- ]?(?:investigations?|studies)\b[^:]{0,120}:", re.I,
)
_NUMBERED_ARM = re.compile(r"(?<!\d)(\d{1,2})\)\s*")
_SEX_ONLY_SUBSTUDIES = re.compile(
    r"\bsub[- ]?(?:investigations?|studies)\s+(\d{1,2})"
    r"(?:\s*(?:to|through|-)\s*(\d{1,2}))?\s+"
    r"(?:were|was)\s+(?:conducted\s+in|limited\s+to|restricted\s+to)\s+"
    r"(women|men|females|males)\s*,?\s*only\b", re.I,
)
_EXPOSURE_FILLER = frozenset({
    "a", "an", "the", "regular", "frequent", "daily", "higher", "high", "lower",
    "low", "use", "usage", "users", "consumption", "consuming", "intake", "eating",
})


def _exposure_arm_population_mismatch(claim: ClaimSnapshot, document: PubMedDocument) -> str | None:
    """Detect explicit sex restriction of the numbered arm containing the exposure.

    A mixed-sex document is not evidence that *every* intervention arm included
    both sexes. No warning is inferred from demographics alone: the source must
    label a numbered intervention arm and explicitly restrict that arm's group.
    """

    if claim.pico is None or not claim.pico.population or not claim.pico.intervention_or_exposure:
        return None
    population = claim.pico.population.casefold()
    male = bool(re.search(r"\b(?:men|males?|boys?)\b", population))
    female = bool(re.search(r"\b(?:women|females?|girls?)\b", population))
    if male == female:
        return None
    exposure_head = re.split(
        r"\b(?:in|among)\b", claim.pico.intervention_or_exposure,
        maxsplit=1, flags=re.I,
    )[0]
    anchor = next((word.casefold() for word in re.findall(r"[^\W_]+", exposure_head)
                   if word.casefold() not in _EXPOSURE_FILLER and len(word) > 2), None)
    if anchor is None:
        return None
    source = document.abstract or ""
    intro = _NUMBERED_SUBSTUDY_INTRO.search(source)
    if intro is None:
        return None
    list_text = source[intro.end():intro.end() + 800]
    positions = tuple(_NUMBERED_ARM.finditer(list_text))
    exposure_arms: set[int] = set()
    for index, match in enumerate(positions):
        end = positions[index + 1].start() if index + 1 < len(positions) else len(list_text)
        arm_text = list_text[match.end():end].split(";", 1)[0]
        arm_text = re.split(r"\.\s+(?=[A-Z][a-z])", arm_text, maxsplit=1)[0]
        if re.search(rf"(?<!\w){re.escape(anchor)}(?!\w)", arm_text, re.I):
            exposure_arms.add(int(match.group(1)))
    if not exposure_arms:
        return None
    incompatible: set[int] = set()
    for match in _SEX_ONLY_SUBSTUDIES.finditer(source):
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if not 1 <= start <= end <= 20:
            continue
        arm_sex = match.group(3).casefold()
        if (male and arm_sex in {"women", "females"}) or (
            female and arm_sex in {"men", "males"}
        ):
            incompatible.update(range(start, end + 1))
    if exposure_arms <= incompatible:
        return ("female_exposure_arm_only_vs_male_claim" if male else
                "male_exposure_arm_only_vs_female_claim")
    return None


def explicit_animal_subject(text: str) -> bool:
    """Recognize only clearly named nonhuman subjects, never infer species."""

    return bool(_EXPLICIT_ANIMAL.search(text))


def classify_study_design(document: PubMedDocument) -> tuple[StudyDesign, str]:
    types = {value.casefold() for value in document.publication_types}
    terms = {value.casefold() for value in document.mesh_terms}
    if "animals" in terms and "humans" not in terms:
        return "animal_study", "pubmed_mesh:animals_without_humans"
    if explicit_animal_subject(document.title) and not _EXPLICIT_HUMAN.search(document.title):
        return "animal_study", "title_explicit_animal_subject"
    for label, design in _PUBTYPE_RULES:
        if label in types:
            return design, f"pubmed_publication_type:{label}"
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
        r"\b(humans?|people|patients?|adults?|children|pediatric|pregnan\w*|"
        r"men|women|males?|females?)\b",
        population,
    ))
    if human_claim and document.study_design == "animal_study":
        flags.append("animal_to_human")
    if human_claim and document.study_design == "in_vitro":
        flags.append("in_vitro_to_clinical")
    adult_claim = bool(re.search(r"\b(?:adults?|men|women|males?|females?)\b", population))
    child_claim = bool(re.search(r"\b(children|child|pediatric|infants?)\b", population))
    pediatric_terms = bool({"child", "infant", "adolescent"} & terms)
    pediatric_title = bool(re.search(r"\b(?:infants?|children|pediatric)\b", title))
    adult_terms = bool({"adult", "middle aged", "aged"} & terms)
    if adult_claim and (pediatric_terms or pediatric_title) and not adult_terms:
        flags.append("pediatric_vs_adult")
    if child_claim and "adult" in terms and "child" not in terms:
        flags.append("pediatric_vs_adult")
    male_claim = bool(re.search(r"\b(?:men|males?|boys?)\b", population))
    female_claim = bool(re.search(r"\b(?:women|females?|girls?)\b", population))
    female_only = ("female" in terms or "women" in terms or bool(re.search(
        r"\b(?:women|female|postmenopausal)\b", title
    ))) and not ("male" in terms or "men" in terms or bool(re.search(
        r"\b(?:men|male)\b", title
    )))
    male_only = ("male" in terms or "men" in terms or bool(re.search(
        r"\b(?:men|male)\b", title
    ))) and not ("female" in terms or "women" in terms or bool(re.search(
        r"\b(?:women|female)\b", title
    )))
    if male_claim and female_only:
        flags.append("female_only_vs_male_claim")
    if female_claim and male_only:
        flags.append("male_only_vs_female_claim")
    arm_mismatch = _exposure_arm_population_mismatch(claim, document)
    if arm_mismatch:
        flags.append(arm_mismatch)
    if "non-pregnant" in population and "pregnancy" in terms:
        flags.append("pregnancy_population_mismatch")
    if claim.claim_type == "prevention" and re.search(r"\btreatment of\b", title):
        flags.append("prevention_vs_treatment")
    if claim.claim_type == "treatment" and re.search(r"\bprevention of\b", title):
        flags.append("prevention_vs_treatment")
    return tuple(flags)


def annotate_study_quality(claim: ClaimSnapshot, document: PubMedDocument) -> PubMedDocument:
    from app.retrieval.analysis_design import characterize_analysis

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
        "relationship_analysis": characterize_analysis(claim, classified),
        "quality_prior": prior,
        "quality_factors": {
            "study_design_base": base, "human_evidence": human_evidence,
            "integrity_multiplier": integrity_multiplier,
            "applicability_multiplier": applicability_multiplier,
        },
        "applicability_warnings": flags,
    })
