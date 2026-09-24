"""Bounded extraction latency and safe retry behavior without a live provider."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

import httpx
import pytest

from app.adapters.claim_extractor import MiriClaimExtractor
from app.core.errors import ExternalCapabilityError

SOURCE = "Vitamin C prevents the common cold."
Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]


def _reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _valid_reply() -> httpx.Response:
    return _reply(json.dumps({
        "claims": [{
            "raw_span": SOURCE, "span_start": 0, "span_end": len(SOURCE),
            "claim_type": "prevention",
        }]
    }))


def _adapter(
    monkeypatch: pytest.MonkeyPatch,
    handler: Handler,
    *,
    attempt_seconds: float = 0.05,
    total_seconds: float = 0.3,
) -> tuple[MiriClaimExtractor, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return await handler(request)

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        MiriClaimExtractor,
        "build_client",
        lambda self: httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(10)),
    )
    adapter = MiriClaimExtractor(
        service_name="fixture", base_url="http://gateway.example/v1",
        timeout_seconds=attempt_seconds, total_timeout_seconds=total_seconds,
    )
    return adapter, requests


def test_first_attempt_timeout_then_second_succeeds(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    attempts = 0

    async def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            await asyncio.sleep(0.2)
        return _valid_reply()

    adapter, requests = _adapter(monkeypatch, respond)
    with caplog.at_level(logging.INFO):
        result = asyncio.run(adapter.extract(text=SOURCE, language="en"))

    assert result.claims[0].raw_span == SOURCE
    assert len(requests) == 2
    assert "failure_type=attempt_timeout" in caplog.text
    assert "attempt_number=2" in caplog.text
    assert "retry_occurred=True" in caplog.text
    assert SOURCE not in caplog.text


def test_first_empty_response_then_second_succeeds(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    responses = [_reply(""), _valid_reply()]

    async def respond(_request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    adapter, requests = _adapter(monkeypatch, respond)
    with caplog.at_level(logging.INFO):
        result = asyncio.run(adapter.extract(text=SOURCE, language="en"))

    assert result.claims[0].raw_span == SOURCE
    assert len(requests) == 2
    assert "failure_type=empty_response" in caplog.text
    assert "retry_occurred=True" in caplog.text
    assert "failure_type=none" in caplog.text


def test_both_attempts_timeout_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    async def respond(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        return _valid_reply()

    adapter, requests = _adapter(monkeypatch, respond)
    with caplog.at_level(logging.WARNING), pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text=SOURCE, language="en"))

    assert len(requests) == 2
    assert error.value.code == "claim_extractor_timeout"
    assert error.value.status_code == 504
    assert caplog.text.count("failure_type=attempt_timeout") == 2


def test_both_empty_responses_fail_closed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    async def respond(_request: httpx.Request) -> httpx.Response:
        return _reply("")

    adapter, requests = _adapter(monkeypatch, respond)
    with caplog.at_level(logging.WARNING), pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text=SOURCE, language="en"))

    assert len(requests) == 2
    assert error.value.code == "claim_extractor_invalid_response"
    assert error.value.status_code == 502
    assert caplog.text.count("failure_type=empty_response") == 2


def test_total_deadline_stops_a_retry(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    attempts = 0

    async def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return _reply("")
        await asyncio.sleep(0.3)
        return _valid_reply()

    adapter, requests = _adapter(
        monkeypatch, respond, attempt_seconds=0.25, total_seconds=0.08
    )
    with caplog.at_level(logging.WARNING), pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text=SOURCE, language="en"))

    assert len(requests) == 2
    assert error.value.code == "claim_extractor_deadline_exceeded"
    assert error.value.status_code == 504
    assert "failure_type=total_deadline_exceeded" in caplog.text
    assert "retry_occurred=True" in caplog.text


def test_normal_response_uses_one_attempt(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    async def respond(_request: httpx.Request) -> httpx.Response:
        return _valid_reply()

    adapter, requests = _adapter(monkeypatch, respond)
    with caplog.at_level(logging.INFO):
        result = asyncio.run(adapter.extract(text=SOURCE, language="en"))

    assert result.claims[0].raw_span == SOURCE
    assert len(requests) == 1
    assert "attempt_number=1" in caplog.text
    assert "retry_occurred=False" in caplog.text
    assert "failure_type=none" in caplog.text
