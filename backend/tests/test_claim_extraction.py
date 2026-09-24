import pytest

from app.adapters.claim_extractor import (
    ClaimExtractionPayload,
    ExtractedClaimCandidate,
    validate_claim_candidates,
)
from app.core.errors import ExternalCapabilityError


def test_validated_claims_keep_exact_source_offsets() -> None:
    source = "Vitamin C prevents colds."
    payload = ClaimExtractionPayload(
        claims=[
            ExtractedClaimCandidate(
                raw_span="Vitamin C prevents colds.",
                span_start=0,
                span_end=len(source),
                normalized_claim="Vitamin C prevents common colds.",
                claim_type="preventive",
                verifiability=0.9,
                resolved_from_span_start=0,
                resolved_from_span_end=9,
            )
        ]
    )

    claims = validate_claim_candidates(payload=payload, source_text=source, maximum_claims=20)

    assert claims[0].raw_span == source[claims[0].span_start : claims[0].span_end]
    assert (
        source[claims[0].resolved_from_span_start : claims[0].resolved_from_span_end] == "Vitamin C"
    )


def test_claims_with_provider_invented_offsets_are_rejected() -> None:
    payload = ClaimExtractionPayload(
        claims=[ExtractedClaimCandidate(raw_span="Different", span_start=0, span_end=9)]
    )

    with pytest.raises(ExternalCapabilityError, match="spans"):
        validate_claim_candidates(payload=payload, source_text="Source text", maximum_claims=20)
