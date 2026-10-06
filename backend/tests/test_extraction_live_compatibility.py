"""Provider quirks and development-only visible response diagnostics."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from app.adapters.claim_extractor import OpenAICompatibleClaimExtractor
from app.core.debug_trace import model_events, record_model_event, trace_analysis
from app.core.errors import ExternalCapabilityError

SOURCE = "High blood pressure causes stroke."


def _response(*, content: str, reasoning: str = "private provider reasoning") -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {
        "content": content, "reasoning": reasoning,
    }}]})


def _claim(*, span_end: int) -> str:
    return json.dumps({"claims": [{
        "raw_span": SOURCE, "span_start": 0, "span_end": span_end,
        "claim_type": "causal", "pico": {
            "intervention_or_exposure": "High blood pressure", "outcome": "stroke",
        },
    }]})


def _adapter(monkeypatch: pytest.MonkeyPatch, replies: list[httpx.Response]
             ) -> tuple[OpenAICompatibleClaimExtractor, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return replies[len(requests) - 1]

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        OpenAICompatibleClaimExtractor, "build_client",
        lambda self: httpx.AsyncClient(transport=transport),
    )
    return OpenAICompatibleClaimExtractor(
        service_name="fixture", base_url="http://provider.example/v1", model="fixture-model",
    ), requests


def test_json_instruction_and_unique_span_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, requests = _adapter(monkeypatch, [_response(content=_claim(span_end=31))])
    analysis_id = uuid4()

    with trace_analysis(analysis_id, enabled=True):
        result = asyncio.run(adapter.extract(text=SOURCE, language="en"))

    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert "Return exactly one JSON object" in body["messages"][0]["content"]
    assert result.claims[0].span_end == len(SOURCE)
    events = model_events(analysis_id)
    assert events[0]["status"] == "calling"
    assert events[-1]["status"] == "responded"
    assert SOURCE in str(events[-1]["response_excerpt"])
    assert "private provider reasoning" not in str(events)
    assert "Return exactly one JSON object" not in str(events)


def test_empty_claims_for_explicit_relation_retry_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, requests = _adapter(monkeypatch, [
        _response(content='{"claims":[]}'), _response(content=_claim(span_end=len(SOURCE))),
    ])
    result = asyncio.run(adapter.extract(text=SOURCE, language="en"))
    assert len(requests) == 2
    assert len(result.claims) == 1


def test_repeated_empty_claims_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, requests = _adapter(monkeypatch, [
        _response(content='{"claims":[]}'), _response(content='{"claims":[]}'),
    ])
    with pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text=SOURCE, language="en"))
    assert error.value.code == "claim_extractor_invalid_response"
    assert len(requests) == 2


def test_duplicate_or_invented_spans_are_not_reconciled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = f"{SOURCE} {SOURCE}"
    duplicate = _response(content=_claim(span_end=31))
    adapter, requests = _adapter(monkeypatch, [duplicate, duplicate])
    with pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text=source, language="en"))
    assert error.value.code == "claim_extractor_invalid_response"
    assert len(requests) == 2


def test_debug_trace_preserves_full_response_is_scoped_and_disabled() -> None:
    first = uuid4()
    second = uuid4()
    event = dict(
        role="extraction", provider="fixture", model="test-model", attempt=1,
        status="responded", failure_type=None, http_status=200, elapsed_ms=10,
        response_content="x" * 5000,
    )
    with trace_analysis(first, enabled=True):
        record_model_event(**event)
    with trace_analysis(second, enabled=False):
        record_model_event(**event)
    assert model_events(first)[0]["response_excerpt"] == event["response_content"]
    assert model_events(first)[0]["analysis_id"] == str(first)
    assert model_events(uuid4()) == []
    assert model_events(second) == []
