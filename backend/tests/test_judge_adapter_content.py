"""Judge transport may unwrap one presentation fence, but never repair decisions."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from app.adapters.judge import OpenAICompatibleJudgeProvider, _unwrap_single_json_fence
from app.core.debug_trace import model_events, trace_analysis
from app.judging.models import JudgeSlot
from app.judging.prompt import PreparedJudgeInput
from app.judging.service import DecisionFailure, parse_provider_decision


@pytest.mark.parametrize("content,expected", [
    ('```json\n{"schema_version":"2.0"}\n```', '{"schema_version":"2.0"}'),
    ('```JSON\r\n{"schema_version":"2.0"}\r\n```', '{"schema_version":"2.0"}'),
    ('{"schema_version":"2.0"}', '{"schema_version":"2.0"}'),
    ('Here is JSON:\n```json\n{"schema_version":"2.0"}\n```',
     'Here is JSON:\n```json\n{"schema_version":"2.0"}\n```'),
    ('```json\n{}\n```\n```json\n{}\n```',
     '```json\n{}\n```\n```json\n{}\n```'),
    ('```json\n{"broken":\n```', '```json\n{"broken":\n```'),
    ('```json\n[1,2]\n```', '```json\n[1,2]\n```'),
])
def test_only_one_whole_json_object_fence_is_unwrapped(
    content: str, expected: str,
) -> None:
    assert _unwrap_single_json_fence(content) == expected


def test_adapter_unwraps_ling_fence_but_keeps_raw_debug_and_strict_schema(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    raw_content = '```json\n{"schema_version":"2.0"}\n```'

    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {"content": raw_content}}],
            "usage": {"prompt_tokens": 14, "completion_tokens": 7},
        })

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        "app.adapters.judge.httpx.AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs),
    )
    slot = JudgeSlot(
        slot=1, provider="openai_compatible", model="fixture-ling",
        model_family="fixture", base_url="https://example.invalid/v1",
        request_json_schema=False,
    )
    prepared = PreparedJudgeInput(
        pack_id=uuid4(), pack_hash="a" * 64, selected_ids=("E1",),
        system_prompt="Use only frozen evidence", user_prompt="fixture",
        prompt_hash="b" * 64, input_snapshot_version="judge-input-2.0",
        input_snapshot_hash="c" * 64, input_snapshot_json={},
    )
    analysis_id = uuid4()
    with trace_analysis(analysis_id, enabled=True), caplog.at_level("INFO"):
        result = asyncio.run(OpenAICompatibleJudgeProvider(1).evaluate(slot, prepared))
    assert result.content == '{"schema_version":"2.0"}'
    assert result.input_tokens == 14 and result.output_tokens == 7
    assert model_events(analysis_id)[-1]["response_excerpt"] == raw_content
    assert "category=single_json_fence" in caplog.text
    assert json.loads(result.content)["schema_version"] == "2.0"
    with pytest.raises(DecisionFailure) as error:
        parse_provider_decision(result.content, ("E1",))
    assert error.value.category == "unsupported_label"
