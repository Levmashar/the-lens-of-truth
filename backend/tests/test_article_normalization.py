"""Literal article framing regressions, without model calls or medical labels."""

import pytest

from app.adapters.claim_extractor import ExtractedClaimCandidate, PicoCandidate
from app.pipeline.numeric_effect import numeric_effect
from app.pipeline.pico import normalize_pico
from app.validation.numeric_effects import (
    NumericQuantity,
    NumericSourceFidelity,
    compare_to_claim,
)


def framed(source: str, exposure: str, outcome: str = "melanoma"):
    return normalize_pico(ExtractedClaimCandidate(
        raw_span=source, span_start=0, span_end=len(source), claim_type="association",
        pico=PicoCandidate(intervention_or_exposure=exposure, outcome=outcome),
    ))


@pytest.mark.parametrize("source,proposal,expected", [
    ("Sunscreen users had melanoma.", "sunscreen use", "Sunscreen"),
    ("Non-smokers had melanoma.", "smokers", None),
    ("Drug X users had melanoma.", "Drug X use", "Drug X"),
])
def test_partial_words_and_compounds_cannot_ground_the_original_proposed_phrase(
    source, proposal, expected,
):
    assert framed(source, proposal).intervention_or_exposure == expected
    assert framed(source, proposal).intervention_or_exposure != proposal


def test_literal_grounding_keeps_original_case_and_line_wraps():
    pico = framed("SUNSCREEN\nUSE was associated with Melanoma.", "sunscreen use")
    assert pico.intervention_or_exposure == "SUNSCREEN\nUSE"
    assert pico.outcome == "Melanoma"


@pytest.mark.parametrize("source,proposal,expected", [
    ("People who used sunscreen\nfrequently had melanoma.", "frequent sunscreen use", "sunscreen"),
    ("People who regularly used Drug A had melanoma.", "regular Drug A use", "Drug A"),
    ("People using Device B daily had melanoma.", "daily Device B usage", "Device B"),
    ("People who used sunscreen frequently had melanoma.", "sunscreen use", "sunscreen"),
    ("Device B users had melanoma.", "Device B use", "Device B"),
    ("Frequent Device B users had melanoma.", "frequent Device B use", "Device B"),
])
def test_explicit_usage_can_recover_only_the_already_proposed_literal_core(
    source, proposal, expected,
):
    pico = framed(source, proposal)
    assert pico.intervention_or_exposure == expected
    assert pico.original_claim == source
    assert expected in source


@pytest.mark.parametrize("source,proposal", [
    ("People who used Drug A had melanoma.", "frequent Drug A use"),
    ("People who used Drug A regularly had melanoma.", "daily Drug A use"),
    ("People who used Drug A regularly had melanoma.", "protective Drug A use"),
    ("People who used Drug A regularly had melanoma.", "regular Drug B use"),
    ("Sunscreen users had melanoma.", "frequent sunscreen use"),
    ("People used Drug B; Drug C users had melanoma.", "Drug A use"),
    ("Drug B users had melanoma; Drug A was discussed.", "Drug A use"),
    ("Drug A users frequently developed melanoma.", "frequent Drug A use"),
])
def test_usage_recovery_rejects_unstated_qualifiers_and_unrelated_usage_context(
    source, proposal,
):
    assert framed(source, proposal).intervention_or_exposure is None


@pytest.mark.parametrize("source,bound,direction,kind", [
    ("Up to a 292% increased risk of invasive melanoma for sunscreen users.",
     "292", "increase", "percent_change"),
    ("Drug A reduces mortality by up to 20%.", "20", "decrease", "percent_change"),
    ("At most a 4.5 percentage-point reduction in mortality was reported.",
     "4.5", "decrease", "percentage_points"),
])
def test_explicit_numeric_ceiling_is_preserved_without_an_exact_point(
    source, bound, direction, kind,
):
    effect = numeric_effect(source)
    assert effect is not None and effect.status == "parsed"
    assert effect.kind == kind and effect.direction == direction
    assert effect.value is None and effect.lower_value is None
    assert effect.upper_value == bound
    assert effect.raw_text in source
    assert effect.model_dump(mode="json")["upper_value"] == bound


def test_unspecified_percent_ceiling_does_not_invent_effect_direction():
    effect = numeric_effect("Up to 20% of the participants were adults.")
    assert effect is not None and effect.status == "uncertain"
    assert effect.direction is None and effect.value is None


def test_article_numeric_bound_and_literal_user_exposure_remain_distinct():
    source = "up to a 292% increased risk of invasive\nmelanoma for sunscreen users"
    pico = framed(source, "sunscreen use", "invasive melanoma")
    assert pico.intervention_or_exposure == "sunscreen"
    assert pico.outcome == "invasive\nmelanoma"
    assert pico.numeric_effect is not None
    assert pico.numeric_effect.upper_value == "292" and pico.numeric_effect.value is None


def test_existing_point_comparison_cannot_promote_a_ceiling_to_an_exact_estimate():
    claim = "Sunscreen users had up to a 292% increased melanoma risk."
    quantity = NumericQuantity(values=("292",), kind="percent_change", unit="increase",
                               literal="292% increase")
    fidelity = NumericSourceFidelity(
        status="verified", asserted=quantity, source=quantity,
        source_evidence_ids=("E1",), reason="literal fixture",
    )
    comparison, position = compare_to_claim(
        fidelity, numeric_effect(claim), "292% increase", claim_scope_text=claim,
    )
    assert position == "unresolved"
    assert comparison.reason == "claim_value_unresolved"
