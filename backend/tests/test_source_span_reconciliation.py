"""Whitespace reconciliation must return literal owned source, never paraphrases."""

import pytest

from app.adapters.source_spans import reconcile_unique_source_span


def test_literal_span_keeps_original_unicode_offsets() -> None:
    prefix = "Screenshot \U0001f50e: "
    span = "Vitamin C shortens common-cold duration."
    source = f"{prefix}{span} End."

    assert reconcile_unique_source_span(source, span) == (
        len(prefix), len(prefix) + len(span), span,
    )


@pytest.mark.parametrize("whitespace", ["\n", "\r\n", "\t", "  ", "\u00a0", "\u2003", "\u2028"])
def test_line_wrapping_and_unicode_whitespace_restore_exact_source(whitespace: str) -> None:
    span = f"Sunscreen users had{whitespace}a 292% increased risk."
    source = f"Study: {span} Another sentence."
    proposed = "Sunscreen users had a 292% increased risk."

    result = reconcile_unique_source_span(source, proposed)

    assert result == (len("Study: "), len("Study: ") + len(span), span)
    assert result is not None
    start, end, exact_source = result
    assert source[start:end] == exact_source


def test_provider_whitespace_can_differ_without_rewriting_source() -> None:
    source = "Smoking does not cause lung cancer."
    proposed = "Smoking\t does\nnot  cause\u00a0lung\rcancer."

    assert reconcile_unique_source_span(source, proposed) == (0, len(source), source)


def test_leading_and_trailing_runs_keep_their_complete_source_boundaries() -> None:
    source = "Prefix:\r\n  Smoking causes cancer.\t\nSuffix"
    span = "\r\n  Smoking causes cancer.\t\n"

    assert reconcile_unique_source_span(source, " Smoking causes cancer. ") == (
        len("Prefix:"), len("Prefix:") + len(span), span,
    )


@pytest.mark.parametrize("source, proposed", [
    ("Smoking causes cancer. Smoking causes cancer.", "Smoking causes cancer."),
    ("Smoking causes cancer. Smoking\ncauses cancer.", "Smoking causes cancer."),
    ("Smoking\ncauses cancer. Smoking\tcauses cancer.", "Smoking causes cancer."),
    ("risk risk risk", "risk risk"),
    ("risk\nrisk\trisk", "risk risk"),
    ("aaaa", "aaa"),
])
def test_repeated_and_overlapping_whitespace_equivalent_matches_are_ambiguous(
    source: str, proposed: str,
) -> None:
    assert reconcile_unique_source_span(source, proposed) is None


@pytest.mark.parametrize("proposed", [
    "Sunscreen users had a 92% increased risk.",
    "Sunscreen users had a 292% decreased risk.",
    "Sunscreen users had no 292% increased risk.",
    "Sunscreen users had a 292 percent increased risk.",
    "Sunscreen users had a 292 % increased risk.",
    "Sunscreenusers had a 292% increased risk.",
    "sunscreen users had a 292% increased risk.",
    "Sunscreen users had a 292% increased risk!",
    "Sunscreen users had a 292% increased-risk.",
    "Sunscreen\u200busers had a 292% increased risk.",
    " Sunscreen users had a 292% increased risk.",
    "Sunscreen users had a 292% increased risk. ",
])
def test_altered_content_or_whitespace_insertion_removal_is_rejected(proposed: str) -> None:
    source = "Sunscreen users had\na 292% increased risk."

    assert reconcile_unique_source_span(source, proposed) is None


@pytest.mark.parametrize("source, proposed", [
    ("Vitamin-C prevents colds.", "Vitamin C prevents colds."),
    ("It states 'no reduction'.", "It states \u2018no reduction\u2019."),
    ("Caf\u00e9 consumption increases risk.", "Cafe\u0301 consumption increases risk."),
    ("Smoking does not cause cancer.", "Smoking causes cancer."),
    ("Smoking causes cancer.", ""),
    ("", "Smoking causes cancer."),
])
def test_non_whitespace_normalization_and_empty_spans_are_rejected(
    source: str, proposed: str,
) -> None:
    assert reconcile_unique_source_span(source, proposed) is None
