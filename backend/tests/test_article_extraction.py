"""Source boundaries and unresolved article fragments must stay auditable."""

import pytest

from app.adapters.claim_extractor import (
    ClaimExtractionPayload,
    ExtractedClaimCandidate,
    _reconcile_unique_offsets,
    validate_claim_candidates,
)
from app.core.errors import ExternalCapabilityError


def test_multiline_span_rebinds_only_whitespace_and_discards_stale_antecedent() -> None:
    source = "Intro. People using X\n had higher risk of Y."
    proposed = "People using X had higher risk of Y."
    payload = ClaimExtractionPayload(claims=[ExtractedClaimCandidate(
        raw_span=proposed, span_start=7, span_end=7 + len(proposed),
        resolved_from_span_start=0, resolved_from_span_end=5,
    )])
    bound = _reconcile_unique_offsets(payload, source)
    result = validate_claim_candidates(
        payload=bound, source_text=source, maximum_claims=20,
    )[0]
    assert result.raw_span == source[7:]
    assert result.span_end == len(source)
    assert result.resolved_from_span_start is None
    assert result.resolved_from_span_end is None


@pytest.mark.parametrize("fragment", [
    "plus higher rates of another cancer.",
    "These links held after adjustment.",
    "Those results were reported in the study.",
])
def test_unresolved_article_fragment_does_not_use_model_antecedent(fragment: str) -> None:
    source = "An analysis was described. " + fragment
    start = source.index(fragment)
    payload = ClaimExtractionPayload(claims=[ExtractedClaimCandidate(
        raw_span=fragment, span_start=start, span_end=len(source),
        normalized_claim="A made-up exposure increases cancer risk.",
        resolved_from_span_start=0, resolved_from_span_end=11,
    )])
    result = validate_claim_candidates(
        payload=payload, source_text=source, maximum_claims=20,
    )[0]
    assert result.standalone_status in {"uncertain", "incomplete"}
    assert result.normalized_claim is None
    assert result.resolved_from_span_start is None
    assert result.resolved_from_span_end is None


def test_duplicate_whitespace_equivalent_passages_are_not_arbitrarily_rebound() -> None:
    source = "X\nraises Y. X raises\nY."
    payload = ClaimExtractionPayload(claims=[ExtractedClaimCandidate(
        raw_span="X raises Y.", span_start=1, span_end=12,
    )])
    bound = _reconcile_unique_offsets(payload, source)
    assert bound.claims[0].span_start == 1
    with pytest.raises(ExternalCapabilityError, match="spans"):
        validate_claim_candidates(payload=bound, source_text=source, maximum_claims=20)
