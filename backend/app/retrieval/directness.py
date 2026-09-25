"""Deterministic claim-relationship fit for PubMed titles and abstract passages.

This is a selection heuristic, not entailment, support, or medical correctness.
Only source-grounded PICO wording and confidently linked terminology labels expand
the two core concepts. Every positive/negative contribution is exposed.
"""

import re
from collections import Counter

from app.retrieval.models import (
    ClaimSnapshot,
    PubMedDocument,
    RankedPassage,
    RelationshipDirection,
    RelationshipDirectness,
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+|;\s+")
_BACKGROUND = frozenset({"BACKGROUND", "INTRODUCTION", "OBJECTIVE", "PURPOSE"})
_SUBSTANTIVE = frozenset({"RESULTS", "RESULT", "CONCLUSIONS", "CONCLUSION"})
_METHODS = frozenset({"METHODS", "METHOD", "DESIGN", "PARTICIPANTS"})
_CUES: dict[str, re.Pattern[str]] = {
    "causal": re.compile(
        r"\b(?:caus(?:e|es|ed|al|ation)|risk|inciden(?:ce|t)|hazard|odds|"
        r"predict(?:s|ed|or)?|prospective|cohort|associat\w*)\b", re.I,
    ),
    "association": re.compile(
        r"\b(?:associat\w*|correlat\w*|linked to|odds|hazard|inciden\w*|risk)\b", re.I,
    ),
    "prevention": re.compile(
        r"\b(?:prevent\w*|prophyla\w*|protect\w*|reduc\w* (?:risk|incidence)|"
        r"prevention trial)\b", re.I,
    ),
    "treatment": re.compile(
        r"\b(?:treat\w*|therap\w*|improv\w*|response|efficacy)\b", re.I,
    ),
}
_NEVER_SMOKER = re.compile(
    r"\b(?:never[ -]?(?:smokers?|smoking)|non[ -]?(?:smokers?|smoking)|nonsmokers?)\b",
    re.I,
)
_SMOKING = re.compile(r"\b(?:smoking|smokers?|tobacco)\b", re.I)
_SCREENING_CESSATION = re.compile(r"\b(?:screening|cessation|quit(?:ting)?)\b", re.I)
_POST_CESSATION = re.compile(r"\bafter\s+smoking\s+cessation\b", re.I)
_RISK_FOCUS = re.compile(r"\b(?:risk|inciden\w*|caus\w*|associat\w*|hazard|odds)\b", re.I)
_REVERSE_CONTEXT = re.compile(
    r"\b(?:after|following|post[ -]?|survivors? of|patients? with|"
    r"secondary prevention of)\b", re.I,
)
_MANAGEMENT = re.compile(
    r"\b(?:management|control|lowering|treatment|target|therapy|trajectories)\b", re.I,
)
_QUALIFIERS = frozenset({"frequent", "regular", "daily", "higher", "high", "invasive"})
_USAGE = frozenset({"use", "users", "of", "the"})


def _section_kind(label: str) -> str:
    normalized = label.upper()
    if normalized == "TITLE":
        return "TITLE"
    if (normalized in _SUBSTANTIVE or "RESULT" in normalized
            or "CONCLUSION" in normalized or normalized == "FINDINGS"):
        return "SUBSTANTIVE"
    if normalized in _METHODS or "METHOD" in normalized:
        return "METHODS"
    if normalized in _BACKGROUND or "BACKGROUND" in normalized:
        return "BACKGROUND"
    return "ABSTRACT"


def _aliases(claim: ClaimSnapshot, role: str) -> tuple[str, ...]:
    if claim.pico is None:
        return ()
    source = getattr(claim.pico, role)
    values = [source] if source else []
    for entity in claim.entities:
        if (entity.entity_type == role and entity.mesh_id and not entity.ambiguous
                and entity.match_type in {"exact", "synonym"}):
            values.extend((entity.surface_text, entity.preferred_name))
    # Bounded reduction of non-concept qualifiers in PICO, not vocabulary expansion.
    if source:
        tokens = source.casefold().split()
        reduced = [token for token in tokens if token not in _QUALIFIERS | _USAGE]
        if reduced and len(reduced) < len(tokens):
            values.append(" ".join(reduced))
    return tuple(sorted({value.strip().casefold() for value in values if value and
                         len(value.strip()) >= 3}, key=lambda value: (-len(value), value)))


def _matches(text: str, aliases: tuple[str, ...]) -> bool:
    for alias in aliases:
        pattern = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", re.I)
        for match in pattern.finditer(text):
            if alias == "smoking":
                prefix = text[max(0, match.start() - 8):match.start()].casefold()
                suffix = text[match.end():match.end() + 12].casefold()
                if (prefix.endswith(("never-", "never ", "non-", "non "))
                        or suffix.startswith(("-related", "-associated"))):
                    continue
            return True
    return False


def _sentences(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in _SENTENCE.split(text) if part.strip())


def _proximity(text: str, exposure: tuple[str, ...],
               outcome: tuple[str, ...]) -> tuple[bool, bool]:
    sentences = _sentences(text)
    exposure_indices = {i for i, sentence in enumerate(sentences)
                        if _matches(sentence, exposure)}
    outcome_indices = {i for i, sentence in enumerate(sentences)
                       if _matches(sentence, outcome)}
    same = bool(exposure_indices & outcome_indices)
    adjacent = any(abs(a - b) == 1 for a in exposure_indices for b in outcome_indices)
    return same, adjacent


def _post_outcome_frame(text: str, outcome: tuple[str, ...]) -> bool:
    for alias in outcome:
        target = r"(?<!\w)" + re.escape(alias) + r"(?!\w)"
        if (re.search(r"\b(?:after|following|post[ -]?|prior|previous)\b.{0,85}"
                      + target, text, re.I)
                or re.search(r"\bpatients? with\b.{0,35}" + target, text, re.I)
                or re.search(target + r".{0,35}\b(?:survivors?|patients?|recovery)\b",
                             text, re.I)):
            return True
    return False


def _direction(
    claim: ClaimSnapshot, document: PubMedDocument, exposure: tuple[str, ...],
    outcome: tuple[str, ...], *, incidental: bool, excluded: bool,
    exposure_excluded: bool, covariate_only: bool,
) -> tuple[RelationshipDirection, tuple[str, ...]]:
    title = document.title
    if excluded:
        return "incidental", ("exposure_excluded_population",)
    if exposure_excluded:
        return "incidental", ("exposure_excluded_from_study",)
    if covariate_only:
        return "incidental", ("exposure_used_as_adjustment_covariate",)
    if incidental:
        return "incidental", ("core_concept_incidental",)
    if _POST_CESSATION.search(title) and _matches(title, outcome):
        return "incidental", ("post_cessation_context_not_claim_exposure",)
    if (_matches(title, outcome) and _matches(title, exposure)
            and _SCREENING_CESSATION.search(title)
            and re.search(r"\bscreening\b", title, re.I)
            and re.search(r"\bcessation\b", title, re.I)
            and not re.search(r"\b(?:risk|incidence) of lung cancer\b", title, re.I)):
        return "incidental", ("screening_and_cessation_study_question",)
    if (_matches(title, exposure) and _matches(title, outcome)
            and _post_outcome_frame(title, outcome)):
        return "reverse", ("post_outcome_exposure_measurement",)
    if _matches(title, outcome) and _matches(title, exposure):
        if _REVERSE_CONTEXT.search(title) and _MANAGEMENT.search(title):
            return "reverse", ("post_outcome_management_title",)
        if _SCREENING_CESSATION.search(title) and not _RISK_FOCUS.search(title):
            return "incidental", ("screening_or_cessation_not_risk_question",)
    cue = _CUES.get(claim.claim_type or "")
    if cue is None:
        return "unknown", ()
    for section in document.abstract_sections:
        for sentence in _sentences(section.text):
            if _matches(sentence, exposure) and _matches(sentence, outcome) and cue.search(
                sentence
            ):
                if _post_outcome_frame(sentence, outcome) and _MANAGEMENT.search(sentence):
                    continue
                if _SCREENING_CESSATION.search(sentence) and not _RISK_FOCUS.search(sentence):
                    continue
                return "aligned", ("both_concepts_with_relation_cue",)
    if _matches(title, exposure) and _matches(title, outcome) and cue.search(title):
        return "aligned", ("title_relation_cue",)
    return "unknown", ()


def annotate_directness(
    claim: ClaimSnapshot, documents: tuple[PubMedDocument, ...],
    passages: tuple[RankedPassage, ...],
) -> tuple[tuple[PubMedDocument, ...], tuple[RankedPassage, ...]]:
    """Annotate every auditable source unit using only deterministic text signals."""

    exposure = _aliases(claim, "intervention_or_exposure")
    outcome = _aliases(claim, "outcome")
    if not exposure or not outcome:
        return documents, passages
    by_document: dict[str, list[RankedPassage]] = {}
    for ranked_item in passages:
        by_document.setdefault(ranked_item.passage.document_id, []).append(ranked_item)
    annotated_documents: list[PubMedDocument] = []
    annotated_passages: dict[str, RankedPassage] = {}
    for document in documents:
        items = by_document.get(document.document_id, [])
        title_exposure = _matches(document.title, exposure)
        title_outcome = _matches(document.title, outcome)
        counts: Counter[str] = Counter()
        substantive_exposure = substantive_outcome = False
        background_exposure = background_outcome = False
        same_section = False
        for item in items:
            section = _section_kind(item.passage.section)
            has_e = _matches(item.passage.text, exposure)
            has_o = _matches(item.passage.text, outcome)
            counts["exposure"] += int(has_e)
            counts["outcome"] += int(has_o)
            same_section |= has_e and has_o and section != "TITLE"
            if section == "SUBSTANTIVE":
                substantive_exposure |= has_e
                substantive_outcome |= has_o
            if section == "BACKGROUND":
                background_exposure |= has_e
                background_outcome |= has_o
        background_only_exposure = (
            background_exposure and not title_exposure and not substantive_exposure
            and counts["exposure"] == 1
        )
        background_only_outcome = (
            background_outcome and not title_outcome and not substantive_outcome
            and counts["outcome"] == 1
        )
        # A named excluded population is a stronger signal than a mention of
        # smoking in contextual background, but applies only to smoking claims.
        excluded = bool(_SMOKING.search(" ".join(exposure)) and _NEVER_SMOKER.search(
            document.title + " " + " ".join(
                item.passage.text for item in items
                if _section_kind(item.passage.section) in {"METHODS", "BACKGROUND"}
            )
        ))
        document_text = " ".join(item.passage.text for item in items)
        exposure_excluded = any(re.search(
            r"\b(?:except|excluding|other than)\s+" + re.escape(alias) + r"\b",
            document_text, re.I,
        ) for alias in exposure)
        covariate_only = bool(
            not title_exposure and counts["exposure"] <= 2 and any(re.search(
                r"\badjust(?:ed|ing|ment)?\s+(?:for|by)\b[^.]{0,110}\b"
                + re.escape(alias) + r"\b", document_text, re.I,
            ) for alias in exposure)
        )
        incidental = background_only_exposure or background_only_outcome
        direction, reasons = _direction(
            claim, document, exposure, outcome, incidental=incidental, excluded=excluded,
            exposure_excluded=exposure_excluded, covariate_only=covariate_only,
        )
        for item in items:
            passage = item.passage
            section = _section_kind(passage.section)
            has_e = _matches(passage.text, exposure)
            has_o = _matches(passage.text, outcome)
            same, adjacent = _proximity(passage.text, exposure, outcome)
            cue = _CUES.get(claim.claim_type or "")
            relation_cue = bool(cue and cue.search(passage.text))
            passage_direction: RelationshipDirection = (
                direction if direction in {"reverse", "incidental"} else
                "aligned" if direction == "aligned" and has_e and has_o
                and (relation_cue or section == "TITLE") else "unknown"
            )
            section_bonus = (0.14 if section == "SUBSTANTIVE" else
                             0.04 if section == "METHODS" else
                             -0.08 if section == "BACKGROUND" else 0.0)
            incidental_penalty = 0.24 if (
                (background_only_exposure and has_e) or
                (background_only_outcome and has_o) or
                (covariate_only and has_e)
            ) else 0.0
            exclusion_penalty = 0.35 if excluded or exposure_excluded else 0.0
            direction_adjustment = (0.13 if passage_direction == "aligned" else
                                    -0.30 if passage_direction == "reverse" else
                                    -0.18 if passage_direction == "incidental" else 0.0)
            factors = {
                "exposure_in_passage": float(has_e),
                "outcome_in_passage": float(has_o),
                "both_in_same_sentence": float(same),
                "both_in_adjacent_sentences": float(adjacent),
                "both_in_same_abstract_section": float(same_section and section != "TITLE"
                                                       and has_e and has_o),
                "exposure_elsewhere_in_document": float(not has_e and counts["exposure"] > 0),
                "outcome_elsewhere_in_document": float(not has_o and counts["outcome"] > 0),
                "relation_cue": float(relation_cue),
                "section_weight": section_bonus,
                "incidental_mention_penalty": incidental_penalty,
                "exposure_excluded_penalty": exclusion_penalty,
                "direction_adjustment": direction_adjustment,
            }
            score = round(max(0.0, min(1.0,
                0.06 + 0.14 * has_e + 0.14 * has_o + 0.20 * same
                + 0.08 * adjacent + 0.10 * relation_cue + section_bonus
                + direction_adjustment - incidental_penalty - exclusion_penalty,
            )), 4)
            detail = RelationshipDirectness(
                score=score, direction=passage_direction, factors=factors,
                reasons=reasons if passage_direction != "unknown" else (),
                warnings=(("exposure_excluded_population",) if excluded else
                          ("exposure_excluded_from_study",) if exposure_excluded else ()),
            )
            annotated_passages[item.evidence_id] = item.model_copy(update={
                "relationship_directness": detail,
            })
        strongest = max((item.relationship_directness.score
                         for item in annotated_passages.values()
                         if item.passage.document_id == document.document_id), default=0.0)
        document_factors = {
            "strongest_passage_directness": strongest,
            "exposure_in_title": float(title_exposure),
            "outcome_in_title": float(title_outcome),
            "both_in_same_abstract_section": float(same_section),
            "exposure_in_document": float(counts["exposure"] > 0),
            "outcome_in_document": float(counts["outcome"] > 0),
            "exposure_only_background": float(background_only_exposure),
            "outcome_only_background": float(background_only_outcome),
            "exposure_excluded_population": float(excluded),
            "exposure_excluded_from_study": float(exposure_excluded),
            "exposure_used_as_adjustment_covariate": float(covariate_only),
        }
        document_score = round(max(0.0, min(1.0,
            0.70 * strongest + 0.10 * title_exposure + 0.10 * title_outcome
            + 0.10 * same_section - 0.15 * (incidental or covariate_only)
            - 0.20 * (excluded or exposure_excluded),
        )), 4)
        annotated_documents.append(document.model_copy(update={
            "relationship_directness": RelationshipDirectness(
                score=document_score, direction=direction, factors=document_factors,
                reasons=reasons,
                warnings=(("exposure_excluded_population",) if excluded else
                          ("exposure_excluded_from_study",) if exposure_excluded else ()),
            ),
        }))
    return tuple(annotated_documents), tuple(
        annotated_passages.get(item.evidence_id, item) for item in passages
    )
