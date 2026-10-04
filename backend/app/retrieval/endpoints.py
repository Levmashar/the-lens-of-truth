"""Endpoint directness from frozen title/abstract wording, never result valence."""

import re

from app.retrieval.directness import _aliases, _matches, _section_kind, _sentences
from app.retrieval.models import ClaimSnapshot, EndpointDirectness, PubMedDocument, RankedPassage

_MEASUREMENT_OUTCOME = re.compile(
    r"\b(?:levels?|concentrations?|serum|plasma|blood|biomarkers?|measurements?|"
    r"mass|gain|growth|severity|duration|pressure|glucose|cholesterol)\b", re.I,
)
_MEASUREMENT_CUE = re.compile(
    r"\b(?:levels?|concentrations?|serum|plasma|measur\w*|biomarker\w*|"
    r"baseline|follow.up|adjusted mean|mass|gains?|growth|severity|duration)\b", re.I,
)
_MECHANISM = re.compile(
    r"(?:-like|-associated|-responsive|\s+receptors?|\s+pathways?|"
    r"\s+signall?ing|\s+deficiency)", re.I,
)
_MEASUREMENT_WORDS = frozenset({
    "level", "levels", "concentration", "concentrations", "serum", "plasma",
    "blood", "measurement", "measurements", "change", "changes", "rate", "rates",
    "higher", "lower", "increased", "decreased", "gain", "growth", "mass",
})
_POST_DISEASE_ENDPOINT = re.compile(
    r"\b(?:screening|progression|metastasis|survival|mortality|deaths?|"
    r"treatment|therapy)\b", re.I,
)
_DISEASE_OCCURRENCE = re.compile(
    r"\b(?:risk|inciden\w*|develop\w*|new cases?)\b", re.I,
)
_MUSCLE_SIZE_OUTCOME = re.compile(r"\bmuscl\w*\b.*\b(?:gains?|growth|mass)\b", re.I)
_MUSCLE_GAIN_CUE = re.compile(
    r"\bmuscle\s+(?:gains?|growth)\b|"
    r"\b(?:gains?|growth)\s+(?:(?:in|of|the|lean)\s+){0,3}muscle"
    r"(?:\s+mass)?\b", re.I,
)
_MUSCLE_MASS_CHANGE_CUE = re.compile(
    r"\b(?:increas\w*|decreas\w*|chang\w*)\s+"
    r"(?:(?:in|of|the|lean)\s+){0,3}muscle\s+mass\b|"
    r"\bmuscle\s+mass\s+(?:(?:was|were|is|has|had)\s+){0,2}"
    r"(?:increas\w*|decreas\w*|chang\w*)\b", re.I,
)
_MUSCLE_ENDPOINT_UNMEASURED = re.compile(
    r"\bmuscle\s+(?:gains?|growth|mass)\b.{0,25}"
    r"\b(?:not|never)\s+(?:measur\w*|assess\w*|evaluat\w*)\b", re.I,
)


def _outcome_terms(claim: ClaimSnapshot) -> tuple[tuple[str, ...], bool]:
    if claim.pico is None or not claim.pico.outcome:
        return (), False
    outcome = claim.pico.outcome.casefold()
    measured = bool(_MEASUREMENT_OUTCOME.search(outcome))
    reduced = " ".join(word for word in outcome.split() if word not in _MEASUREMENT_WORDS)
    values = {outcome, *_aliases(claim, "outcome")}
    if reduced and len(reduced) >= 3:
        values.add(reduced)
    return tuple(sorted(values, key=lambda value: (-len(value), value))), measured


def _endpoint_signal(
    text: str, aliases: tuple[str, ...], measured: bool, *, muscle_size: bool = False,
) -> tuple[bool, bool]:
    """Require an outcome mention plus measurement/change for quantitative endpoints."""

    context_only = False
    for sentence in _sentences(text):
        for alias in aliases:
            pattern = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", re.I)
            for mention in pattern.finditer(sentence):
                nearby = sentence[max(0, mention.start() - 28):mention.end() + 35]
                modifier = bool(_MECHANISM.match(sentence[mention.end():]))
                context_only |= modifier
                if modifier:
                    continue
                if muscle_size and not (
                    (_MUSCLE_GAIN_CUE.search(sentence)
                     or _MUSCLE_MASS_CHANGE_CUE.search(sentence))
                    and not _MUSCLE_ENDPOINT_UNMEASURED.search(sentence)
                ):
                    # A generic linked "Muscles" concept plus blood biomarkers
                    # does not establish the asserted gain/growth endpoint.
                    continue
                if measured and not _MEASUREMENT_CUE.search(nearby):
                    continue
                return True, False
    return False, context_only


def annotate_endpoints(
    claim: ClaimSnapshot, documents: tuple[PubMedDocument, ...],
    passages: tuple[RankedPassage, ...],
) -> tuple[tuple[PubMedDocument, ...], tuple[RankedPassage, ...]]:
    """Expose separately scored endpoint fit for every auditable document/passage."""

    outcome, measured = _outcome_terms(claim)
    muscle_size = bool(
        claim.pico and claim.pico.outcome
        and _MUSCLE_SIZE_OUTCOME.search(claim.pico.outcome)
    )
    exposure = _aliases(claim, "intervention_or_exposure")
    if not outcome or not exposure:
        return documents, passages
    by_doc: dict[str, list[RankedPassage]] = {}
    for item in passages:
        by_doc.setdefault(item.passage.document_id, []).append(item)
    annotated_docs: list[PubMedDocument] = []
    annotated_items: dict[str, RankedPassage] = {}
    for document in documents:
        title_signal, title_mechanism = _endpoint_signal(
            document.title, outcome, measured, muscle_size=muscle_size,
        )
        title_exposure = _matches(document.title, exposure)
        post_disease_endpoint = bool(
            not measured and claim.claim_type in {"causal", "association", "prevention"}
            and not _POST_DISEASE_ENDPOINT.search(
                claim.pico.outcome if claim.pico and claim.pico.outcome else ""
            )
            and _POST_DISEASE_ENDPOINT.search(document.title)
            and not _DISEASE_OCCURRENCE.search(document.title)
        )
        sections = by_doc.get(document.document_id, [])
        has_substantive = False
        has_methods = False
        has_background = False
        has_abstract = False
        for item in sections:
            section = _section_kind(item.passage.section)
            text = item.passage.text
            outcome_mentioned = _matches(text, outcome)
            signal, mechanism = _endpoint_signal(
                text, outcome, measured, muscle_size=muscle_size,
            )
            exposure_mentioned = _matches(text, exposure)
            same_sentence = any(
                _matches(sentence, exposure) and _endpoint_signal(
                    sentence, outcome, measured, muscle_size=muscle_size,
                )[0]
                for sentence in _sentences(text)
            )
            has_substantive |= signal and section == "SUBSTANTIVE"
            has_methods |= signal and section == "METHODS"
            has_background |= signal and section == "BACKGROUND"
            has_abstract |= signal and section == "ABSTRACT"
            role = (0.25 if section == "SUBSTANTIVE" else 0.15 if section == "METHODS"
                    else 0.12 if section == "TITLE" else 0.06 if section == "ABSTRACT"
                    else -0.10)
            mechanism_penalty = 0.30 if mechanism and not signal else 0.0
            endpoint_mismatch_penalty = 0.35 if post_disease_endpoint else 0.0
            score = round(max(0.0, min(1.0,
                0.06 * outcome_mentioned + 0.28 * signal + role * signal
                + 0.12 * exposure_mentioned + 0.12 * same_sentence
                + 0.12 * title_signal + 0.08 * title_exposure
                - mechanism_penalty - endpoint_mismatch_penalty,
            )), 4)
            annotated_items[item.evidence_id] = item.model_copy(update={
                "endpoint_directness": EndpointDirectness(
                    score=score,
                    factors={
                        "outcome_mentioned": float(outcome_mentioned),
                        "measured_endpoint_signal": float(signal),
                        "exposure_in_passage": float(exposure_mentioned),
                        "same_sentence": float(same_sentence),
                        "section_component": role if signal else 0.0,
                        "title_endpoint_signal": float(title_signal),
                        "mechanism_only_penalty": mechanism_penalty,
                        "post_disease_endpoint_penalty": endpoint_mismatch_penalty,
                    },
                    reasons=(("endpoint_studied" if signal else "endpoint_not_established"),),
                    warnings=tuple(
                        warning for warning, applies in (
                            ("mechanism_only_mention", mechanism and not signal),
                            ("post_disease_endpoint", post_disease_endpoint),
                        ) if applies
                    ),
                ),
            })
        strongest = max((annotated_items[item.evidence_id].endpoint_directness.score
                         for item in sections), default=0.0)
        background_only = has_background and not (
            title_signal or has_methods or has_substantive or has_abstract
        )
        specific_size_endpoint = bool(
            title_signal or has_methods or has_substantive or has_abstract
        )
        score = round(max(0.0, min(1.0,
            0.65 * strongest + 0.20 * title_signal + 0.10 * has_substantive
            + 0.05 * has_methods - 0.25 * background_only
            - 0.20 * post_disease_endpoint,
        )), 4)
        annotated_docs.append(document.model_copy(update={
            "endpoint_directness": EndpointDirectness(
                score=score,
                factors={
                    "strongest_passage_endpoint": strongest,
                    "quantitative_outcome": float(measured),
                    "endpoint_in_title": float(title_signal),
                    "exposure_in_title": float(title_exposure),
                    "endpoint_in_results": float(has_substantive),
                    "endpoint_in_methods": float(has_methods),
                    "endpoint_only_background": float(background_only),
                    "specific_size_endpoint_required": float(muscle_size),
                    "specific_size_endpoint_present": float(specific_size_endpoint),
                    "post_disease_endpoint_penalty": 0.20 if post_disease_endpoint else 0.0,
                },
                reasons=("endpoint_studied" if score >= 0.5 else "endpoint_indirect",),
                warnings=tuple(
                    warning for warning, applies in (
                        ("mechanism_only_title", title_mechanism and not title_signal),
                        ("post_disease_endpoint", post_disease_endpoint),
                        ("specific_size_endpoint_absent", muscle_size
                         and not specific_size_endpoint),
                    ) if applies
                ),
            ),
        }))
    return tuple(annotated_docs), tuple(
        annotated_items.get(item.evidence_id, item) for item in passages
    )
