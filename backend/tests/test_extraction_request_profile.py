"""Bounded extraction settings and safe provider diagnostics."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from app.adapters.claim_extractor import (
    OpenAICompatibleClaimExtractor,
    _completion_metadata,
)
from app.core.debug_trace import model_events, trace_analysis
from app.core.errors import ExternalCapabilityError


def test_thinking_is_explicit_only_when_configured_and_output_is_bounded() -> None:
    default = OpenAICompatibleClaimExtractor(service_name="fixture", model="fixture")
    assert default.request_options() == {"max_tokens": 8192}
    configured = OpenAICompatibleClaimExtractor(
        service_name="fixture", model="DeepSeek-V4.1-Flash", thinking_enabled=False,
    )
    assert configured.request_options() == {
        "max_tokens": 8192, "thinking": {"type": "disabled"},
    }


def test_unknown_explicit_thinking_profile_fails_before_network() -> None:
    with pytest.raises(ExternalCapabilityError) as error:
        OpenAICompatibleClaimExtractor(
            service_name="fixture", model="fixture", thinking_enabled=False,
        ).request_options()
    assert error.value.code == "claim_extractor_configuration_error"


def test_stop_metadata_discards_untrusted_fields_and_reasoning_text() -> None:
    response = httpx.Response(200, json={
        "choices": [{"finish_reason": {"secret": "hidden"}, "message": {
            "content": "visible", "reasoning_content": "private reasoning",
        }}],
        "usage": {"prompt_tokens": 9, "completion_tokens": True, "total_tokens": -1,
                  "extra": "private", "completion_tokens_details": {"reasoning_tokens": 0}},
    })
    assert _completion_metadata(response) == {
        "finish_reason": "other", "response_char_count": 7,
        "usage": {"prompt_tokens": 9, "reasoning_tokens": 0},
    }


def test_token_cutoff_rejects_even_valid_partial_json_and_records_safe_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "length", "message": {
                "content": '{"claims":[]}', "reasoning_content": "private reasoning",
            }}], "usage": {"prompt_tokens": 10, "completion_tokens": 100},
        })

    monkeypatch.setattr(OpenAICompatibleClaimExtractor, "build_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    adapter = OpenAICompatibleClaimExtractor(
        service_name="fixture", model="DeepSeek-V4.1-Flash",
        base_url="http://fixture/v1", thinking_enabled=False,
    )
    analysis_id = uuid4()
    with trace_analysis(analysis_id, enabled=True), pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text="Smoking causes lung cancer.", language="en"))

    assert error.value.code == "claim_extractor_invalid_response"
    assert len(requests) == 2
    body = json.loads(requests[0].content)
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == 8192
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["ExtractedClaimCandidate"]["required"] == list(
        schema["$defs"]["ExtractedClaimCandidate"]["properties"],
    )
    events = model_events(analysis_id)
    assert events[-1]["failure_type"] == "output_token_limit"
    assert events[-1]["response_metadata"]["finish_reason"] == "length"
    assert "private reasoning" not in str(events)
