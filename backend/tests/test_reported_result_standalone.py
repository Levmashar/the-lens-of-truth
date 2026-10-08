"""Only explicit adjacent reported-result actors can ground coordinated fragments."""

from pathlib import Path

import pytest

from app.pipeline.standalone import StandaloneResult, validate_standalone


def _result(source: str, raw: str) -> StandaloneResult:
    start = source.index(raw)
    return validate_standalone(source, start, start + len(raw))


def test_frozen_article_coordinated_rate_inherits_only_exact_source_group() -> None:
    source = (Path(__file__).parent / "fixtures" / "long_input_sunscreen_20261007.txt").read_text(
        encoding="utf-8",
    )
    raw = "plus higher rates of basal\ncell and squamous cell carcinomas"

    result = _result(source, raw)

    assert result.status == "reconstructed"
    assert result.subject == "sunscreen users"
    assert result.text == (
        "sunscreen users had higher rates of basal\ncell and squamous cell carcinomas."
    )
    assert result.inherited_start is not None and result.inherited_end is not None
    assert source[result.inherited_start:result.inherited_end] == result.subject
    assert "292" not in result.text
    assert "invasive" not in result.text
    assert "cause" not in result.text
    assert "compared" not in result.text
    assert source[309:369] == raw


@pytest.mark.parametrize("coordinator", ["and", "plus"])
@pytest.mark.parametrize("coordinator_in_raw", [True, False])
def test_reported_comparative_result_preserves_literal_actor_and_endpoint(
    coordinator: str, coordinator_in_raw: bool,
) -> None:
    source = (
        "The study reported a 2.92% increased risk of fractures among participants receiving "
        f"treatment, {coordinator} lower rates of hospitalization."
    )
    raw = f"{coordinator} lower rates of hospitalization" if coordinator_in_raw else (
        "lower rates of hospitalization"
    )

    result = _result(source, raw)

    assert result.status == "reconstructed"
    assert result.subject == "participants receiving treatment"
    assert result.text == "participants receiving treatment had lower rates of hospitalization."
    assert result.inherited_start is not None and result.inherited_end is not None
    assert source[result.inherited_start:result.inherited_end] == result.subject
    assert "2.92" not in result.text


@pytest.mark.parametrize("source, raw", [
    (
        "The study showed increased risk of fractures, plus higher rates of hospitalization.",
        "plus higher rates of hospitalization",
    ),
    (
        "The study showed increased risk of fractures for users and patients, "
        "plus higher rates of hospitalization.",
        "plus higher rates of hospitalization",
    ),
    (
        "The study showed increased risk of fractures for those, "
        "plus higher rates of hospitalization.",
        "plus higher rates of hospitalization",
    ),
    (
        "The study did not show increased risk of fractures for users, "
        "plus higher rates of hospitalization.",
        "plus higher rates of hospitalization",
    ),
    (
        "The study might show increased risk of fractures for users, "
        "plus higher rates of hospitalization.",
        "plus higher rates of hospitalization",
    ),
    (
        "The study showed no increased risk of fractures for users, "
        "plus higher rates of hospitalization.",
        "plus higher rates of hospitalization",
    ),
    (
        "The analysis showed increased risk of fractures for users. "
        "Plus higher rates of hospitalization.",
        "Plus higher rates of hospitalization",
    ),
    (
        "Increased risk of fractures for users, plus higher rates of hospitalization.",
        "plus higher rates of hospitalization",
    ),
    (
        "The study showed increased risk of fractures for users, "
        "higher rates of hospitalization.",
        "higher rates of hospitalization",
    ),
    (
        "The study showed increased risk of fractures for improving treatment, "
        "plus higher rates of hospitalization.",
        "plus higher rates of hospitalization",
    ),
    (
        "The study did not show a 2.92% increased risk of fractures for users, "
        "and higher rates of hospitalization.",
        "higher rates of hospitalization",
    ),
    (
        "The study reported a 2.92% increased risk of fractures for users and patients, "
        "and higher rates of hospitalization.",
        "higher rates of hospitalization",
    ),
])
def test_ambiguous_unasserted_or_non_adjacent_reported_fragments_stay_incomplete(
    source: str, raw: str,
) -> None:
    result = _result(source, raw)

    assert result.status in {"incomplete", "uncertain"}
    assert result.text is None
    assert result.inherited_start is None
    assert result.inherited_end is None


def test_existing_verb_coordination_still_uses_its_original_subject() -> None:
    source = "Exercise reduces diabetes risk, and lowers blood pressure."

    result = _result(source, "lowers blood pressure")

    assert result.status == "reconstructed"
    assert result.subject == "Exercise"
    assert result.text == "Exercise lowers blood pressure."
