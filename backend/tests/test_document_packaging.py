"""Prompt compression preserves all evidence/quantities and source ownership."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from app.adapters import document_models
from app.document.evaluation import (
    JUDGE_INSTRUCTIONS,
    JUDGE_VERSION,
    GroupJudgeResponse,
    JudgeItem,
    document_snapshot,
    parse_group_items,
)
from app.document.packaging import expand_quantity_view, source_view
from app.judging.models import JudgeSlot
from tests.test_document_evaluation import pack, plan, run


def test_quantity_table_round_trips_the_entire_frozen_catalog_without_omission():
    evidence = pack(contrary_trial=True)
    frozen = document_snapshot(uuid4(), evidence)
    view = source_view(evidence, frozen)
    assert (
        expand_quantity_view(view["source_quantity_catalog"]) == frozen["source_quantity_catalog"]
    )
    assert view["source_units"] == frozen["source_units"]
    assert {d["document_id"] for d in view["documents"]} == {
        unit["document_id"] for unit in frozen["source_units"]
    }
    assert all("abstract" not in d and "crossref" not in d for d in view["documents"])
    assert len(json.dumps(view)) < len(
        json.dumps(source_view(evidence, frozen, version="document-group-input-1.0"))
    )


@pytest.mark.parametrize("wrapper", ["```json\n{}\n```", "```\n{}\n```"])
def test_one_exact_json_fence_is_transport_framing_not_an_invalid_shared_envelope(wrapper):
    data = {"version": JUDGE_VERSION, "group_id": "G1", "items": []}
    raw = wrapper.replace("{}", json.dumps(data))
    parsed, failures = parse_group_items(
        raw, version=JUDGE_VERSION, group_id="G1", expected=("A1",), item_type=JudgeItem
    )
    assert parsed == {}
    assert failures == {"A1": "missing_assertion_response"}
    with pytest.raises(ValueError):
        parse_group_items(
            raw,
            version=JUDGE_VERSION,
            group_id="G1",
            expected=("A1",),
            item_type=JudgeItem,
            allow_fence=False,
        )


@pytest.mark.parametrize(
    "raw",
    [
        'Here is JSON: {"version":"document-judge-1.0","group_id":"G1","items":[]}',
        '```json\n{"version":"document-judge-1.0","group_id":"G1","items":[]}\n```\nMore prose',
        '{"version":"document-judge-1.0","group_id":"G1","items":[]} {}',
    ],
)
def test_prose_multiple_envelopes_or_partial_fences_cannot_be_salvaged(raw):
    with pytest.raises(ValueError):
        parse_group_items(
            raw, version=JUDGE_VERSION, group_id="G1", expected=("A1",), item_type=JudgeItem
        )


def test_coverage_is_guaranteed_inclusion_not_an_exclusive_citation_namespace(monkeypatch):
    import asyncio

    from app.document import evaluation
    from app.document.evaluation import evaluate_group
    from tests.test_document_evaluation import fake_transport, settings

    document = plan()
    evidence = pack()
    monkeypatch.setattr(evaluation, "complete_group", fake_transport())
    results = asyncio.run(
        evaluate_group(
            document,
            document.groups[0],
            evidence,
            {"status": "identified", "matched_document_ids": ["pubmed:123"]},
            uuid4(),
            settings(),
            per_assertion_evidence_ids={"A1": ()},
        )
    )
    assert all(result["items"]["A1"]["position"] == "supported" for result in results)


def test_foreign_unit_is_still_rejected_when_coverage_is_nonexclusive(monkeypatch):
    def change(data, payload):
        data["items"][0]["statements"][0]["source_unit_ids"] = ["E999.U1"]

    results = run(monkeypatch, mutate_judge=change)
    assert all(result["items"]["A1"]["position"] is None for result in results)


def test_qwen_json_requirement_and_safe_provider_exception_are_audited(monkeypatch):
    original_client = httpx.AsyncClient
    secret = "fixture-do-not-export"
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Missing JSON instruction " + secret,
                    "type": "invalid_request_error",
                    "code": "400",
                    "request_headers": {"Authorization": secret},
                }
            },
        )

    monkeypatch.setattr(
        document_models.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    slot = JudgeSlot(
        slot=1,
        provider="fixture",
        model="Qwen3.5-Plus",
        model_family="qwen",
        base_url="https://fixture.invalid/v1",
        api_key=secret,
    )
    result = asyncio.run(
        document_models.complete_group(
            slot,
            role="judge_1",
            operation="document_judge",
            system=JUDGE_INSTRUCTIONS,
            payload={},
            schema=GroupJudgeResponse,
            timeout=1,
        )
    )
    assert "json" in " ".join(message["content"] for message in captured[0]["messages"]).lower()
    assert result["http_status"] == 400
    assert result["provider_error"]["message"] == "Missing JSON instruction [REDACTED]"
    assert "request_headers" not in result["provider_error"]
    assert secret not in json.dumps(result)
