"""Small, controlled claim taxonomy; this is wording, not a truth verdict."""

import re
from enum import StrEnum


class ClaimType(StrEnum):
    CAUSAL = "causal"
    ASSOCIATION = "association"
    PREVENTION = "prevention"
    TREATMENT = "treatment"
    DIAGNOSTIC = "diagnostic"
    SAFETY = "safety"
    RECOMMENDATION = "recommendation"
    STATISTICAL_OR_STUDY_RESULT = "statistical_or_study_result"
    METHODOLOGY = "methodology"
    OTHER = "other"


_ASSOCIATION = re.compile(
    r"\b(?:is|are|was|were|has been|have been)\s+"
    r"(?:associated|correlated)\s+with\b|\blinked\s+to\b|"
    r"\b(?:association|correlation)\s+between\b",
    re.IGNORECASE,
)
_CAUSAL = re.compile(r"\b(?:cause|causes|caused|causing)\b", re.IGNORECASE)


def explicit_relation(source: str) -> ClaimType | None:
    """Lock only unambiguous English wording; leave other languages to the model."""

    if _ASSOCIATION.search(source):
        return ClaimType.ASSOCIATION
    if _CAUSAL.search(source):
        return ClaimType.CAUSAL
    return None


def legacy_claim_type(value: str | None) -> ClaimType | None:
    """Safely read old rows without allowing their free-form labels into new output."""

    if value is None:
        return None
    aliases = {
        "preventive": ClaimType.PREVENTION,
        "causal_numeric": ClaimType.CAUSAL,
        "risk_association": ClaimType.ASSOCIATION,
        "study_description": ClaimType.STATISTICAL_OR_STUDY_RESULT,
        "reported_statistical_result": ClaimType.STATISTICAL_OR_STUDY_RESULT,
        "treatment_recommendation": ClaimType.RECOMMENDATION,
    }
    if value in aliases:
        return aliases[value]
    try:
        return ClaimType(value)
    except ValueError:
        return ClaimType.OTHER
