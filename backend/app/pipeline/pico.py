"""Ground the extractor's structured PICO proposal in one atomic claim."""

import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.adapters.claim_extractor import ExtractedClaimCandidate
from app.pipeline.claim_types import ClaimType, legacy_claim_type
from app.pipeline.standalone import validate_standalone

if TYPE_CHECKING:
    from app.pipeline.completeness import NormalizationQuality

NormalizationStatus = Literal[
    "pending", "unresolved", "pico_only", "partially_linked", "partial", "normalized"
]

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
        values[field] = (
            _grounded_outcome(value, candidate.raw_span) if field == "outcome"
            else _grounded_value(value, candidate.raw_span)
        )
    if shared_clause is not None:
        # The first clause supplies the exact exposure for a subject-ellipsis
        # second clause; neither a model paraphrase nor an unrelated antecedent does.
        values["intervention_or_exposure"] = shared_clause[0]
        if proposed is not None and proposed.population is not None:
            values["population"] = _grounded_value(proposed.population, shared_clause[0])
        if values["population"] is None:
            stated_population = re.search(
                r"\b(?:men|women|adults?|children|males?|females?)\b",
                shared_clause[0], re.I,
            )
            if stated_population is not None:
                values["population"] = stated_population.group()
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
    if source_text is None:
        return None
    if source_text[candidate.span_start:candidate.span_end] != candidate.raw_span:
        return None
    result = validate_standalone(source_text, candidate.span_start, candidate.span_end)
    return (result.subject, result.outcome) if (
        result.status == "reconstructed" and result.subject and result.outcome
    ) else None


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


def _grounded_outcome(value: str | None, source: str) -> str | None:
    """Keep exact endpoint words when a model inflects only a relation verb."""

    exact = _grounded_value(value, source)
    if exact is not None or value is None:
        return exact
    remainder = re.sub(
        r"^(?:increased|decreased|raised|lowered|reduced|caused|prevented|"
        r"improved|worsened|higher|lower|more|less)\s+",
        "", value.strip(), count=1, flags=re.I,
    )
    if remainder == value.strip():
        return None
    return _grounded_value(remainder, source)
