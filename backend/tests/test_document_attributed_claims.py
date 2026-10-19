"""Attribution is preserved without excluding the factual medical proposition."""

import pytest

from app.document.planner import DocumentPlanProposal, build_document_plan
from tests.test_document_planner import proposal


@pytest.mark.parametrize(
    "text",
    [
        "Some commentators argue that Agent X prevents disease Y.",
        'An author says, "Agent X halves the incidence of disease Y."',
        "The results are cited as evidence that Agent X is proven to prevent disease Y.",
    ],
)
def test_attributed_quoted_and_indirect_medical_claims_are_checkable_without_changing_source(text):
    data = proposal(text, [text]).model_dump(mode="json")
    data["assertions"][0].update(
        kind="commentary",
        pico={
            "intervention_or_exposure": "Agent X",
            "outcome": "disease Y",
            "claim_type": "prevention",
        },
    )
    plan = build_document_plan(text, DocumentPlanProposal.model_validate(data))
    item = plan.assertions[0]
    assert item.kind == "general_medical_assertion" and item.checkable
    assert item.planning_status == "ready"
    assert item.source_text == text and item.study_id is None
    assert "attributed_medical_assertion:A1" in plan.warnings


def test_subjective_commentary_and_source_notes_remain_uncheckable():
    text = "Some commentators say that this research is fascinating."
    data = proposal(text, [text]).model_dump(mode="json")
    data["assertions"][0]["kind"] = "commentary"
    item = build_document_plan(text, DocumentPlanProposal.model_validate(data)).assertions[0]
    assert item.kind == "commentary" and not item.checkable


def test_one_link_assigned_to_multiple_assertions_cannot_escape_per_assertion_ownership():
    from tests.test_document_planner import source_span

    first, second = (
        "The review found Agent X reduced disease duration by 7% in adults",
        "16% in children.",
    )
    text = first + " and " + second
    data = proposal(text, [first, second]).model_dump(mode="json")
    for a in data["assertions"]:
        a["context_link_ids"] = ["L1"]
        a["pico"] = {"intervention_or_exposure": "Agent X", "outcome": "disease duration"}
    data["context_links"] = [
        {
            "link_id": "L1",
            "reference": source_span(text, "The review"),
            "target": None,
            "relationship": "study_reference",
            "resolved": False,
        }
    ]
    plan = build_document_plan(text, DocumentPlanProposal.model_validate(data))
    child = plan.assertion("A2")
    assert child.pico.intervention_or_exposure == "Agent X"
    assert child.pico.outcome == "disease duration"
    for a in plan.assertions:
        for lid in a.context_link_ids:
            link = next(link for link in plan.context_links if link.link_id == lid)
            assert any(
                s.start <= link.reference.start < link.reference.end <= s.end for s in a.spans
            )
