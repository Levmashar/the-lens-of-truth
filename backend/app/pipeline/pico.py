"""Ground the extractor's structured PICO proposal in one atomic claim."""

import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.adapters.claim_extractor import ExtractedClaimCandidate
from app.pipeline.claim_types import ClaimType, legacy_claim_type

if TYPE_CHECKING:
    from app.pipeline.completeness import NormalizationQuality

NormalizationStatus = Literal[
    "pending", "unresolved", "pico_only", "partially_linked", "partial", "normalized"
]

_COORDINATED_VERB = (
    r"(?:causes?|caused|increases?|increased|raises?|raised|elevates?|elevated|"
    r"reduces?|reduced|decreases?|decreased|lowers?|lowered|prevents?|prevented|"
    r"improves?|improved|worsens?|worsened|results?\s+in)"
)


class NormalizedPico(BaseModel):
    """Claim framing, never evidence or a medical-truth assessment."""

    model_config = ConfigDict(extra="forbid")

    original_claim: str = Field(min_length=1)
    population: str | None = None
    intervention_or_exposure: str | None = None
    comparator: str | None = None
    outcome: str | None = None
    timeframe: str | None = None
    claim_type: ClaimType | None = None

    @model_validator(mode="before")
    @classmethod
    def read_legacy_claim_type(cls, value: object) -> object:
        if isinstance(value, dict) and isinstance(value.get("claim_type"), str):
            return {**value, "claim_type": legacy_claim_type(value["claim_type"])}
        return value


def normalize_pico(
    candidate: ExtractedClaimCandidate, *, source_text: str | None = None,
) -> NormalizedPico:
    """Ground PICO in the atomic span or an unambiguous coordinated antecedent.

    The existing model adapter produces structured PICO alongside claim extraction.
    Only a narrow, source-verified shared subject may be carried from an adjacent
    clause. Other cross-claim leakage and invented details remain rejected.
    """

    proposed = candidate.pico
    shared_clause = _coordinated_clause(candidate, source_text)
    values: dict[str, str | None] = {}
    for field in ("population", "intervention_or_exposure", "comparator", "outcome", "timeframe"):
        value = getattr(proposed, field) if proposed is not None else None
        values[field] = _grounded_value(value, candidate.raw_span)
    if shared_clause is not None:
        # The first clause supplies the exact exposure for a subject-ellipsis
        # second clause; neither a model paraphrase nor an unrelated antecedent does.
        values["intervention_or_exposure"] = shared_clause[0]
        if values["outcome"] is None:
            # The second clause itself explicitly supplies the outcome. This
            # recovery is deliberately limited to verified coordination.
            values["outcome"] = shared_clause[1]
    return NormalizedPico.model_validate(
        {
            "original_claim": candidate.raw_span,
            **values,
            "claim_type": candidate.claim_type,
        }
    )


def _coordinated_clause(
    candidate: ExtractedClaimCandidate, source_text: str | None,
) -> tuple[str, str] | None:
    if source_text is None or candidate.resolved_from_span_start is None or (
        candidate.resolved_from_span_end is None
    ):
        return None
    start = candidate.resolved_from_span_start
    end = candidate.resolved_from_span_end
    if not 0 <= start < end <= candidate.span_start < candidate.span_end <= len(source_text):
        return None
    if source_text[candidate.span_start:candidate.span_end] != candidate.raw_span:
        return None
    separator = re.search(r"\s*,?\s*and\s+$", source_text[start:candidate.span_start], re.I)
    if separator is None:
        return None
    second = re.fullmatch(
        rf"\s*{_COORDINATED_VERB}\s+(?P<outcome>[^.;:!?]+?)[.!?]?",
        candidate.raw_span, re.I,
    )
    if second is None:
        return None
    antecedent_end = start + separator.start()
    antecedent = source_text[start:antecedent_end]
    match = re.fullmatch(
        rf"(?P<subject>[^,.;:!?]{{1,120}}?)\s+{_COORDINATED_VERB}\s+[^,.;:!?]+",
        antecedent, re.I,
    )
    if match is None:
        return None
    subject = match.group("subject").strip()
    subject_end = start + match.end("subject")
    # Extractors may point at the full prior clause or a word-aligned prefix
    # of the shared subject. Neither pointer licenses an unrelated clause.
    pointer_is_subject_prefix = (
        end <= subject_end
        and (end == subject_end or source_text[end].isspace())
    )
    if not (pointer_is_subject_prefix or end == antecedent_end):
        return None
    if not subject or re.search(r"\b(?:and|or)\b", subject, re.I):
        return None
    outcome = second.group("outcome").strip()
    return (subject, outcome) if outcome else None


def normalize_stored_pico(
    *, raw_text: str, claim_type: str | None,
    population: str | None, intervention_or_exposure: str | None,
    comparator: str | None, outcome: str | None, timeframe: str | None,
) -> NormalizedPico:
    """Re-ground legacy flat PICO slots without invoking a model or adding facts."""

    return NormalizedPico(
        original_claim=raw_text,
        population=_grounded_value(population, raw_text),
        intervention_or_exposure=_grounded_value(intervention_or_exposure, raw_text),
        comparator=_grounded_value(comparator, raw_text),
        outcome=_grounded_value(outcome, raw_text),
        timeframe=_grounded_value(timeframe, raw_text),
        claim_type=legacy_claim_type(claim_type),
    )


def normalization_status(
    pico: NormalizedPico, *, linked_count: int, mention_count: int,
    quality: "NormalizationQuality | None" = None,
) -> NormalizationStatus:
    """Make incomplete vocabulary coverage explicit for downstream retrieval."""

    if quality is not None and (
        quality.required_slots_missing or quality.missing_explicit_concepts
    ):
        return "partial"
    if not any(
        (pico.population, pico.intervention_or_exposure, pico.comparator, pico.outcome)
    ):
        return "unresolved"
    if linked_count == 0:
        return "pico_only"
    if quality is not None and (
        "source_terminology_scan_unavailable" in quality.normalization_warnings
        or "source_terminology_scan_truncated" in quality.normalization_warnings
    ):
        return "partial"
    if linked_count < mention_count:
        return "partially_linked"
    return "normalized"


def _grounded_value(value: str | None, source: str) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    # Allow harmless whitespace differences, but never an absent term or paraphrase.
    parts = re.split(r"\s+", stripped)
    pattern = r"\s+".join(re.escape(part) for part in parts)
    match = re.search(pattern, source, flags=re.IGNORECASE)
    return match.group() if match else None
