"""Fail-closed eligibility for source-grounded evidence work."""

from collections.abc import Mapping

from pydantic import ValidationError

from app.pipeline.claim_types import ClaimType
from app.pipeline.completeness import NormalizationQuality
from app.pipeline.pico import NormalizedPico

_REQUIRES_EXPOSURE_AND_OUTCOME = frozenset({
    ClaimType.CAUSAL, ClaimType.ASSOCIATION, ClaimType.PREVENTION,
    ClaimType.TREATMENT, ClaimType.DIAGNOSTIC, ClaimType.SAFETY,
})
_UNSAFE_SCAN_WARNINGS = frozenset({
    "source_terminology_scan_unavailable", "source_terminology_scan_truncated",
    "legacy_not_audited",
})


def ready_for_evidence(
    status: str, *, pico_json: Mapping[str, object] | None,
    quality_json: Mapping[str, object] | None,
) -> bool:
    """Let complete partial terminology links proceed, never incomplete framing."""

    if status == "normalized":
        return True
    if status != "partially_linked" or pico_json is None or quality_json is None:
        return False
    audited_fields = {
        "required_slots_missing", "missing_explicit_concepts", "normalization_warnings",
    }
    if not audited_fields.issubset(quality_json):
        return False
    try:
        pico = NormalizedPico.model_validate(pico_json)
        quality = NormalizationQuality.model_validate(quality_json)
    except (ValidationError, ValueError, TypeError):
        return False
    if quality.required_slots_missing or quality.missing_explicit_concepts:
        return False
    if _UNSAFE_SCAN_WARNINGS.intersection(quality.normalization_warnings):
        return False
    if pico.claim_type in _REQUIRES_EXPOSURE_AND_OUTCOME and (
        not pico.intervention_or_exposure or not pico.outcome
    ):
        return False
    return True
