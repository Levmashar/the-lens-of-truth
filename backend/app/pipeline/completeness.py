"""Deterministic, source-grounded normalization completeness checks."""

import re

from pydantic import BaseModel, ConfigDict, Field

from app.medical.entities import MedicalEntity
from app.medical.mesh import (
    IndexedMeshProvider,
    MeshMatch,
    MeshProvider,
    UnconfiguredMeshProvider,
)
from app.pipeline.claim_types import ClaimType
from app.pipeline.pico import NormalizedPico

_GENERIC_TERMS = frozenset({
    "risk", "study", "studies", "people", "person", "use", "users", "rate",
    "rates", "health", "illness", "disease", "effect", "effects", "result",
    "results", "higher", "lower", "frequent", "exposure", "invasive",
})
_REQUIRED_PAIR = frozenset({
    ClaimType.CAUSAL, ClaimType.ASSOCIATION, ClaimType.PREVENTION,
    ClaimType.TREATMENT, ClaimType.DIAGNOSTIC, ClaimType.SAFETY,
})


class NormalizationQuality(BaseModel):
    """Coverage is lexical MeSH coverage, not evidence or clinical correctness."""

    model_config = ConfigDict(extra="forbid")

    normalization_coverage: float | None = Field(default=None, ge=0, le=1)
    missing_explicit_concepts: tuple[str, ...] = ()
    required_slots_missing: tuple[str, ...] = ()
    ambiguous_concepts: tuple[str, ...] = ()
    normalization_warnings: tuple[str, ...] = ()
    terminology_version: str | None = None
    terminology_sha256: str | None = None


def assess_completeness(
    pico: NormalizedPico,
    entities: tuple[MedicalEntity, ...],
    mesh: MeshProvider,
) -> NormalizationQuality:
    """Compare strong official source matches against grounded slots and mentions."""

    required: list[str] = []
    if pico.claim_type in _REQUIRED_PAIR:
        if pico.intervention_or_exposure is None:
            required.append("intervention_or_exposure")
        if pico.outcome is None:
            required.append("outcome")

    matches = _salient_matches(mesh.find_mentions(pico.original_claim))
    slot_values = (
        pico.population, pico.intervention_or_exposure, pico.comparator,
        pico.outcome, pico.timeframe,
    )
    represented = [
        match for match in matches
        if any(value and _contains(value, match.surface_text) for value in slot_values)
        or any(_contains(entity.surface_text, match.surface_text) for entity in entities)
    ]
    missing = tuple(
        match.surface_text for match in matches if match not in represented
    )
    ambiguous = tuple(
        match.surface_text for match in matches
        if len({item.mesh_id for item in mesh.lookup(match.surface_text)}) > 1
    )
    warnings: list[str] = []
    if required:
        warnings.append("required_pico_slots_missing")
    if missing:
        warnings.append("explicit_medical_concepts_not_represented")
    if ambiguous or any(entity.ambiguous for entity in entities):
        warnings.append("ambiguous_terminology")
    if isinstance(mesh, UnconfiguredMeshProvider):
        warnings.append("source_terminology_scan_unavailable")
    if len(pico.original_claim) > 256:
        warnings.append("source_terminology_scan_truncated")
    return NormalizationQuality(
        normalization_coverage=(round(len(represented) / len(matches), 3) if matches else None),
        missing_explicit_concepts=missing,
        required_slots_missing=tuple(required),
        ambiguous_concepts=ambiguous,
        normalization_warnings=tuple(warnings),
        terminology_version=mesh.release if isinstance(mesh, IndexedMeshProvider) else None,
        terminology_sha256=(
            mesh.source_sha256 if isinstance(mesh, IndexedMeshProvider) else None
        ),
    )


def _salient_matches(matches: tuple[MeshMatch, ...]) -> tuple[MeshMatch, ...]:
    selected: list[MeshMatch] = []
    for match in sorted(matches, key=lambda item: (-(item.end - item.start), item.start)):
        if match.match_type not in {"exact", "synonym"} or match.confidence < 0.9:
            continue
        surface = match.surface_text.casefold().strip()
        if surface in _GENERIC_TERMS or len(surface) < 3:
            continue
        if any(match.start < item.end and match.end > item.start for item in selected):
            continue
        selected.append(match)
    return tuple(sorted(selected, key=lambda item: item.start))


def _contains(haystack: str, needle: str) -> bool:
    pattern = r"\s+".join(re.escape(part) for part in needle.split())
    return bool(re.search(pattern, haystack, flags=re.IGNORECASE))
