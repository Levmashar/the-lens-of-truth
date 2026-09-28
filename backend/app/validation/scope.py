"""Conservative PICO and relationship-strength guards over frozen metadata/text."""

import re

from app.pipeline.claim_types import ClaimType
from app.retrieval.models import ClaimSnapshot, PubMedDocument, RankedPassage
from app.validation.models import RelationAlignment, ScopeAlignment
from app.validation.numeric import extract_quantities

VERSION = "scope-relation-1.0"
_ADULT = re.compile(r"\b(?:adults?|men|women)\b", re.I)
_CHILD = re.compile(r"\b(?:children|child|pediatric|paediatric|infants?|adolescents?)\b", re.I)
_PREGNANT = re.compile(r"\b(?:pregnan\w*|maternal)\b", re.I)
_ANIMAL = re.compile(r"\b(?:mice|mouse|rats?|murine|animal(?:s| model)?)\b", re.I)
_HUMAN = re.compile(r"\b(?:humans?|patients?|people|adults?|children|participants?)\b", re.I)
_VITRO = re.compile(r"\b(?:in[ -]vitro|cell(?:s| line| culture)?)\b", re.I)
_PREVENT = re.compile(r"\b(?:prevent\w*|prophyla\w*|before (?:developing|onset))\b", re.I)
_TREAT = re.compile(
    r"\b(?:treat(?:ed|ing|s)?|treatment of|therap\w*|management|"
    r"after (?:diagnosis|onset))\b", re.I,
)
_ASSOCIATION = re.compile(r"\b(?:associat\w*|correlat\w*|linked\s+to)\b", re.I)
_NO_CAUSALITY = re.compile(
    r"(?:causal(?:ity)?|cause and effect)\s+(?:cannot|could not|can not|"
    r"not|was not)\s+(?:be\s+)?(?:inferred|established|determined)", re.I,
)
_CAUSAL = re.compile(r"\b(?:caus\w*|prevent\w*|reduc\w*|increas\w*)\b", re.I)


def _contains(text: str, phrase: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(phrase.casefold()) + r"(?!\w)",
                          text.casefold()))


def _slot_present(claim: ClaimSnapshot, name: str, source: str) -> bool:
    if claim.pico is None:
        return False
    phrase = getattr(claim.pico, name)
    if phrase is None:
        return False
    if _contains(source, phrase):
        return True
    if name == "intervention_or_exposure":
        reduced = re.sub(r"\b(?:frequent|regular|daily|use|users|of|the)\b", "", phrase,
                         flags=re.I).strip()
        if reduced and _contains(source, " ".join(reduced.split())):
            return True
    for entity in claim.entities:
        if (entity.entity_type == name and entity.mesh_id and not entity.ambiguous
                and entity.match_type in {"exact", "synonym"}):
            if any(_contains(source, term) for term in
                   (entity.surface_text, entity.preferred_name or "") if term):
                return True
    return False


def compare_scope(
    claim: ClaimSnapshot, document: PubMedDocument, ranked: RankedPassage,
) -> ScopeAlignment:
    """Only explicit mismatches are fatal; absent slots are not manufactured."""

    source = ranked.passage.text
    passage_text = source
    population = claim.pico.population if claim.pico else None
    claim_text = claim.raw_text
    if population:
        if _ADULT.search(population) and (
            (_CHILD.search(source) and not _ADULT.search(source))
            or document.study_design == "animal_study"
        ):
            return ScopeAlignment.MISMATCH
        if _CHILD.search(population) and (
            (_ADULT.search(source) and not _CHILD.search(source))
            or document.study_design == "animal_study"
        ):
            return ScopeAlignment.MISMATCH
        if _PREGNANT.search(population) and not _PREGNANT.search(source):
            return ScopeAlignment.PARTIAL
    if _HUMAN.search(claim_text) and (document.study_design in {"animal_study", "in_vitro"}
                                      or (_ANIMAL.search(source) and not _HUMAN.search(source))
                                      or (_VITRO.search(source) and not _HUMAN.search(source))):
        return ScopeAlignment.MISMATCH
    if document.study_design in {"animal_study", "in_vitro"}:
        return ScopeAlignment.PARTIAL
    claim_type = claim.claim_type or (claim.pico.claim_type if claim.pico else None)
    if (claim_type == ClaimType.PREVENTION and _TREAT.search(passage_text)
            and not _PREVENT.search(passage_text)):
        return ScopeAlignment.MISMATCH
    if (claim_type == ClaimType.TREATMENT and _PREVENT.search(passage_text)
            and not _TREAT.search(passage_text)):
        return ScopeAlignment.MISMATCH
    if claim_type in {ClaimType.CAUSAL, ClaimType.ASSOCIATION}:
        outcome = claim.pico.outcome if claim.pico else None
        post_outcome = bool(outcome and re.search(
            r"\b(?:after|post[ -]?|survivors? of)\s+(?:the\s+)?" + re.escape(outcome),
            passage_text, re.I,
        ))
        if (post_outcome and re.search(r"\b(?:management|treat\w*|therap\w*)\b",
                                       passage_text, re.I)
                and not re.search(r"\b(?:risk of|incidence of)\b", passage_text, re.I)):
            return ScopeAlignment.MISMATCH
    if claim.pico is None:
        return ScopeAlignment.UNCERTAIN
    if claim.pico.comparator and not _slot_present(claim, "comparator", source):
        compared = re.search(r"\bcompared\s+(?:with|to)\s+([^.;,]+)", source, re.I)
        if compared and not _contains(compared.group(1), claim.pico.comparator):
            return ScopeAlignment.MISMATCH
    for name in ("comparator", "outcome"):
        phrase = getattr(claim.pico, name)
        if phrase and not _slot_present(claim, name, source):
            explicit = re.search(rf"\b{name}\s*[:=]\s*([^.;,]+)", source, re.I)
            if explicit and not _contains(explicit.group(1), phrase):
                return ScopeAlignment.MISMATCH
            return ScopeAlignment.PARTIAL
    if claim.pico.timeframe and not _contains(source, claim.pico.timeframe):
        expected = [item for item in extract_quantities(claim.pico.timeframe)
                    if item.kind == "duration"]
        observed = [item for item in extract_quantities(source) if item.kind == "duration"]
        if (len(expected) == len(observed) == 1 and expected[0].unit == observed[0].unit
                and expected[0].values != observed[0].values):
            return ScopeAlignment.MISMATCH
        return ScopeAlignment.PARTIAL
    if claim.pico.intervention_or_exposure and not _slot_present(
        claim, "intervention_or_exposure", source,
    ):
        return ScopeAlignment.PARTIAL
    return ScopeAlignment.ALIGNED


def compare_relation(
    claim: ClaimSnapshot, document: PubMedDocument, ranked: RankedPassage,
) -> RelationAlignment:
    """Association-only evidence cannot by itself validate causal support."""

    claim_type = claim.claim_type or (claim.pico.claim_type if claim.pico else None)
    source = ranked.passage.text
    if ranked.relationship_directness.direction == "reverse":
        return RelationAlignment.REVERSE
    if claim_type == ClaimType.CAUSAL:
        observational = document.study_design in {
            "cohort", "case_control", "cross_sectional", "observational",
        }
        if _NO_CAUSALITY.search(source) or (observational and _ASSOCIATION.search(source)):
            return RelationAlignment.WEAKER_THAN_CLAIM
        if _ASSOCIATION.search(source) and not _CAUSAL.search(source):
            return RelationAlignment.WEAKER_THAN_CLAIM
        if document.study_design in {"randomized_controlled_trial", "clinical_trial"}:
            return RelationAlignment.ALIGNED
        return RelationAlignment.UNCERTAIN
    if claim_type == ClaimType.ASSOCIATION:
        if _ASSOCIATION.search(source) or _CAUSAL.search(source):
            return RelationAlignment.ALIGNED
        return RelationAlignment.UNCERTAIN
    if claim_type == ClaimType.PREVENTION:
        return (RelationAlignment.ALIGNED if _PREVENT.search(source)
                else RelationAlignment.UNCERTAIN)
    if claim_type == ClaimType.TREATMENT:
        return (RelationAlignment.ALIGNED if _TREAT.search(source)
                else RelationAlignment.UNCERTAIN)
    return RelationAlignment.UNCERTAIN
