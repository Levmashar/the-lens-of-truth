"""Exact document coverage, context, grouping and single planning request tests."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from app.adapters.claim_extractor import OpenAICompatibleClaimExtractor
from app.core.config import Settings
from app.core.errors import ExternalCapabilityError
from app.document import planner
from app.document.models import DocumentPlan, SourceSpan
from app.document.planner import DocumentPlanProposal, build_document_plan


def source_span(text: str, fragment: str, start: int = 0) -> dict[str, object]:
    offset = text.index(fragment, start)
    return {"start": offset, "end": offset + len(fragment), "text": fragment}


def proposal(text: str, fragments: list[str], **updates: object) -> DocumentPlanProposal:
    assertions = []
    cursor = 0
    for index, fragment in enumerate(fragments, 1):
        span = source_span(text, fragment, cursor)
        cursor = int(span["end"])
        assertions.append(
            {
                "assertion_id": f"A{index}",
                "kind": "reported_study_fact",
                "spans": [span],
                "pico": {},
                "risk_class": "standard",
            }
        )
    data = {
        "assertions": assertions,
        "groups": [
            {
                "group_id": "G1",
                "title": "Study findings",
                "assertion_ids": [a["assertion_id"] for a in assertions],
            }
        ],
    }
    data.update(updates)
    return DocumentPlanProposal.model_validate(data)


def test_document_detection_preserves_single_claim_path() -> None:
    assert not planner.should_use_document_mode("Smoking causes lung cancer.")
    assert not planner.should_use_document_mode("One statement " + "context " * 60 + ".")
    assert planner.should_use_document_mode("First study " + "context " * 40 + ". Next result.")


def test_grounded_context_and_methodological_assertions_keep_full_source() -> None:
    fragments = [
        "Study Alpha tested Agent X in 470 adults.",
        "It found that Agent X users had more outcome Y.",
        "The study adjusted for age.",
    ]
    text = "\n".join(fragments)
    data = proposal(text, fragments).model_dump(mode="json")
    for assertion in data["assertions"]:
        assertion["study_id"] = "T1"
    data["assertions"][0]["kind"] = "sample_size"
    data["assertions"][1]["pico"] = {
        "intervention_or_exposure": "Agent X",
        "outcome": "outcome Y",
        "population": "470 adults",
        "comparator": "placebo",
    }
    data["assertions"][1]["context_link_ids"] = ["L1"]
    data["assertions"][2]["kind"] = "methodology"
    data["assertions"][2]["context_link_ids"] = ["L2"]
    data["groups"][0]["study_id"] = "T1"
    data["context_links"] = [
        {
            "link_id": f"L{index}",
            "reference": source_span(text, reference),
            "target": source_span(text, fragments[0]),
            "relationship": "study_reference",
            "resolved": True,
        }
        for index, reference in enumerate(("It", "The study"), 1)
    ]
    plan = build_document_plan(text, DocumentPlanProposal.model_validate(data))
    assert plan.original_text == text
    assert plan.assertion("A2").source_text == fragments[1]
    assert plan.assertion("A2").pico.population == "470 adults"
    assert plan.assertion("A2").pico.comparator is None
    assert plan.assertion("A1").pico.claim_type == "statistical_or_study_result"
    assert plan.assertion("A3").pico.claim_type == "methodology"
    assert all(a.checkable and a.planning_status == "ready" for a in plan.assertions)
    assert DocumentPlan.model_validate_json(plan.model_dump_json()) == plan


def test_unlinked_antecedents_and_partial_word_pico_cannot_ground_fields() -> None:
    first, second = "Study Alpha enrolled adults.", "Agent X users had outcome Y."
    text = first + " " + second
    data = proposal(text, [first, second]).model_dump(mode="json")
    data["assertions"][1]["pico"] = {
        "population": "adults",
        "intervention_or_exposure": "Agent X use",
    }
    plan = build_document_plan(text, DocumentPlanProposal.model_validate(data))
    assert plan.assertion("A2").pico.population is None
    assert plan.assertion("A2").pico.intervention_or_exposure is None


def test_unresolved_source_reference_is_preserved_not_invented() -> None:
    text = "It increased outcome Y."
    data = proposal(text, [text]).model_dump(mode="json")
    data["assertions"][0]["context_link_ids"] = ["L1"]
    data["context_links"] = [
        {
            "link_id": "L1",
            "reference": source_span(text, "It"),
            "target": None,
            "relationship": "shared_exposure",
            "resolved": False,
        }
    ]
    result = build_document_plan(text, DocumentPlanProposal.model_validate(data))
    assert result.assertion("A1").planning_status == "unresolved"
    assert result.assertion("A1").pico.intervention_or_exposure is None


def test_wrong_offsets_only_repaired_for_unique_literal_source() -> None:
    text = "Agent X\nusers had outcome Y."
    data = proposal(text, [text]).model_dump(mode="json")
    data["assertions"][0]["spans"][0] = {
        "start": 3,
        "end": 29,
        "text": "Agent X users had outcome Y.",
    }
    plan = build_document_plan(text, DocumentPlanProposal.model_validate(data))
    assert plan.assertion("A1").spans == (SourceSpan(start=0, end=len(text), text=text),)
    data["assertions"][0]["spans"][0]["text"] = "Agent Z users had outcome Y."
    with pytest.raises(ValueError, match="absent or ambiguous"):
        build_document_plan(text, DocumentPlanProposal.model_validate(data))


def test_uncovered_source_is_explicit_unresolved_item() -> None:
    text = "Agent X had outcome Y. More clinical evidence is claimed."
    plan = build_document_plan(text, proposal(text, ["Agent X had outcome Y."]))
    assert plan.assertions[-1].source_text == "More clinical evidence is claimed."
    assert plan.assertions[-1].kind == "unclassified"
    assert plan.assertions[-1].planning_status == "unresolved"
    assert "planner_uncovered_source" in plan.assertions[-1].uncertainty_reasons


def test_group_overflow_splits_without_dropping_context_or_assertions() -> None:
    fragments = [f"Endpoint {index} was reported." for index in range(17)]
    text = "\n".join(fragments)
    data = proposal(text, fragments).model_dump(mode="json")
    data["groups"][0]["context_spans"] = [source_span(text, fragments[0])]
    plan = build_document_plan(text, DocumentPlanProposal.model_validate(data))
    assert [len(g.assertion_ids) for g in plan.groups] == [8, 8, 1]
    assert len(plan.assertions) == 17
    assert all(group.context_spans == plan.groups[0].context_spans for group in plan.groups)


def test_verbatim_repeat_shares_investigation_but_retains_both_source_spans() -> None:
    fragment = "Agent X increased outcome Y."
    text = fragment + "\n" + fragment
    plan = build_document_plan(text, proposal(text, [fragment, fragment]))
    assert len(plan.assertions) == 1
    assert len(plan.assertions[0].spans) == 2
    assert plan.groups[0].assertion_ids == ("A1",)


def test_same_wording_in_distinct_studies_is_not_deduplicated() -> None:
    fragment = "Agent X increased outcome Y."
    text = fragment + "\n" + fragment
    data = proposal(text, [fragment, fragment]).model_dump(mode="json")
    for index, assertion in enumerate(data["assertions"], 1):
        assertion["study_id"] = f"T{index}"
    data["groups"] = [
        {
            "group_id": f"G{i}",
            "title": f"Study {i}",
            "study_id": f"T{i}",
            "assertion_ids": [f"A{i}"],
        }
        for i in (1, 2)
    ]
    assert len(build_document_plan(text, DocumentPlanProposal.model_validate(data)).assertions) == 2


@pytest.mark.parametrize(
    "second",
    [
        "Agent X did not increase outcome Y.",
        "Agent X increased outcome Z.",
        "Agent X increased outcome Y by 40%.",
    ],
)
def test_endpoint_polarity_and_number_differences_cannot_be_deduplicated(second: str) -> None:
    first = "Agent X increased outcome Y."
    text = first + " " + second
    plan = build_document_plan(text, proposal(text, [first, second]))
    assert len(plan.assertions) == 2


def test_unverified_repetition_does_not_discard_medical_statement() -> None:
    fragments = ["Agent X increased outcome Y.", "Agent X increased outcome Z."]
    text = " ".join(fragments)
    data = proposal(text, fragments).model_dump(mode="json")
    data["assertions"][1].update({"kind": "repetition", "duplicate_of": "A1"})
    plan = build_document_plan(text, DocumentPlanProposal.model_validate(data))
    assert plan.assertion("A2").kind == "unclassified"
    assert plan.assertion("A2").planning_status == "unresolved"
    assert len(plan.assertions) == 2


def test_frozen_fragmented_paid_plan_recovers_exact_source_and_one_study_group() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    text = (fixtures / "document_sunscreen_20261007.txt").read_text(encoding="utf-8")
    raw = (fixtures / "document_planner_fragmented_20261007.json").read_text(encoding="utf-8-sig")
    plan = build_document_plan(text, DocumentPlanProposal.model_validate_json(raw))
    assert len(plan.assertions) == 11
    assert len(plan.groups) == 1
    assert plan.assertion("A1").source_text.startswith("A large study drawing")
    assert "470,000" in plan.assertion("A1").source_text
    assert "up to a 292%" in plan.assertion("A4").source_text
    assert plan.assertion("A4").pico.numeric_effect.upper_value == "292"
    assert plan.assertion("A4").pico.numeric_effect.value is None
    assert "sunburn history" in plan.assertion("A6").source_text
    assert plan.assertion("A6").pico.claim_type == "methodology"
    assert all(a.planning_status == "ready" for a in plan.assertions if a.checkable)
    assert all(text[s.start : s.end] == s.text for a in plan.assertions for s in a.spans)
    assert all(link.resolved for link in plan.context_links)


def test_saved_screenshot_plan_isolates_commentary_attribution_and_repairs_literal_link() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    text = (fixtures / "document_screenshot_326b6a1c.txt").read_text(encoding="utf-8")
    raw = (fixtures / "document_planner_326b6a1c.json").read_text(encoding="utf-8")
    plan = build_document_plan(text, DocumentPlanProposal.model_validate_json(raw))
    assert len(plan.assertions) == 11
    assert all(a.planning_status == "ready" for a in plan.assertions if a.checkable)
    assert plan.assertion("A8").study_id == plan.assertion("A11").study_id == "S1"
    assert plan.assertion("A8").planning_status == "not_checkable"
    assert "L2" in plan.assertion("A4").context_link_ids
    assert "L2" not in plan.assertion("A5").context_link_ids
    assert all(link.resolved for link in plan.context_links)
    assert any(w.startswith("context_link_owner_rebound:L2:A5->A4") for w in plan.warnings)
    assert all(text[s.start : s.end] == s.text for a in plan.assertions for s in a.spans)


@pytest.mark.parametrize(
    "kind",
    [
        "reported_study_fact",
        "methodology",
        "sample_size",
        "general_medical_assertion",
        "interpretation",
        "unclassified",
    ],
)
def test_factual_group_attribution_stays_strict_and_names_offending_item(kind: str) -> None:
    text = "Study Alpha reported outcome Y."
    data = proposal(text, [text]).model_dump(mode="json")
    data["assertions"][0].update(kind=kind, study_id="S1")
    with pytest.raises(ValueError, match=r"G1/A1.*group=None.*assertion='S1'"):
        build_document_plan(text, DocumentPlanProposal.model_validate(data))


def test_absent_reference_marks_only_declared_owner_unresolved() -> None:
    first, second = "Agent X had outcome Y.", "It had outcome Z."
    text = first + " " + second
    data = proposal(text, [first, second]).model_dump(mode="json")
    data["assertions"][1]["context_link_ids"] = ["L1"]
    data["context_links"] = [
        {
            "link_id": "L1",
            "reference": {"start": len(first) + 1, "end": len(first) + 3, "text": "They"},
            "target": source_span(text, "Agent X"),
            "relationship": "shared_exposure",
            "resolved": True,
        }
    ]
    plan = build_document_plan(text, DocumentPlanProposal.model_validate(data))
    assert plan.assertion("A1").planning_status == "ready"
    assert plan.assertion("A2").planning_status == "unresolved"
    assert plan.context_links == ()
    assert "unresolved_context_reference:L1" in plan.warnings


@pytest.mark.parametrize("failure", ["unknown_group", "duplicate_group", "unknown_link"])
def test_shared_plan_corruption_fails_entire_contract(failure: str) -> None:
    text = "Agent X had outcome Y."
    data = proposal(text, [text]).model_dump(mode="json")
    if failure == "unknown_group":
        data["groups"][0]["assertion_ids"] = ["A2"]
    elif failure == "duplicate_group":
        data["groups"].append(deepcopy(data["groups"][0]))
    else:
        data["assertions"][0]["context_link_ids"] = ["L99"]
    with pytest.raises(ValueError):
        build_document_plan(text, DocumentPlanProposal.model_validate(data))


def test_complete_source_limit_and_high_risk_preserved() -> None:
    text = "Agent X treats disease Y."
    data = proposal(text, [text]).model_dump(mode="json")
    data["assertions"][0]["risk_class"] = "high"
    plan = build_document_plan(text, DocumentPlanProposal.model_validate(data))
    assert plan.assertions[0].risk_class == "high"
    with pytest.raises(ValueError, match="20000"):
        build_document_plan("x" * 20_001, DocumentPlanProposal.model_validate(data))


@pytest.mark.parametrize("finish_reason", ["stop", "length"])
def test_planner_makes_one_configured_request_and_never_salvages_truncation(
    monkeypatch: pytest.MonkeyPatch,
    finish_reason: str,
) -> None:
    text = "Agent X\nusers had outcome Y."
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": finish_reason,
                        "message": {
                            "content": proposal(text, [text]).model_dump_json(),
                            "reasoning_content": "hidden reasoning",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 30,
                    "total_tokens": 50,
                    "hidden": "private",
                    "invalid": True,
                },
            },
        )

    adapter = OpenAICompatibleClaimExtractor(
        service_name="fixture",
        model="DeepSeek-V4.1-Flash",
        base_url="http://fixture/v1",
        api_key="test-secret",
        thinking_enabled=False,
    )
    monkeypatch.setattr(planner, "get_claim_extractor", lambda _: adapter)
    monkeypatch.setattr(
        OpenAICompatibleClaimExtractor,
        "build_client",
        lambda _: httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
        ),
    )
    settings = Settings(_env_file=None)
    if finish_reason == "length":
        with pytest.raises(ExternalCapabilityError, match="reliably"):
            asyncio.run(planner.plan_document(text, settings))
    else:
        plan = asyncio.run(planner.plan_document(text, settings))
        assert plan.planning_audit["attempt_count"] == 1
        assert plan.planning_audit["usage"] == {
            "prompt_tokens": 20,
            "completion_tokens": 30,
            "total_tokens": 50,
        }
        assert "hidden reasoning" not in str(plan.planning_audit)
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == 8192
    assert text in body["messages"][1]["content"]
    assert body["response_format"]["json_schema"]["strict"] is True
    assert requests[0].url == "http://fixture/v1/chat/completions"
