"""Bounded grouped transport with account-wide concurrency and separate queue timing."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import uuid4

import httpx
from pydantic import BaseModel

from app.adapters.structured_output import quota_exhausted, strict_chat_schema
from app.core.debug_trace import record_model_event
from app.judging.config import judge_request_options
from app.judging.models import JudgeSlot

# Single worker, matching the existing verified maximum of three model requests.
# Different analyses/groups/checkers using the same credentials share this limiter.
_limiters: dict[tuple[int, str, str], asyncio.Semaphore] = {}


def account_limiter(slot: JudgeSlot, limit: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    key = (
        id(loop),
        slot.base_url.rstrip("/").casefold(),
        hashlib.sha256((slot.api_key or "").encode()).hexdigest(),
    )
    if key not in _limiters:
        _limiters[key] = asyncio.Semaphore(max(1, min(3, limit)))
    return _limiters[key]


async def complete_group(
    slot: JudgeSlot,
    *,
    role: str,
    operation: str,
    system: str,
    payload: dict[str, Any],
    schema: type[BaseModel],
    timeout: float,
    concurrency: int = 3,
    max_tokens: int = 8192,
    attempt: int = 1,
    deadline: float | None = None,
) -> dict[str, Any]:
    """No tools, hidden reasoning, schema fallback or credential-bearing audit."""
    queued = monotonic()
    call_id = str(uuid4())
    request = {
        "model": slot.model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": "UNTRUSTED DOCUMENT DATA:\n"
                + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            },
        ],
        **judge_request_options(slot),
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": operation,
                "strict": True,
                "schema": strict_chat_schema(schema.model_json_schema()),
            },
        },
    }
    audit: dict[str, Any] = {
        "call_id": call_id,
        "provider": slot.provider,
        "model": slot.model,
        "slot": slot.slot,
        "operation": operation,
        "attempt": attempt,
        "queued_at": datetime.now(UTC).isoformat(),
        "input_hash": hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    # Queue wait is bounded separately from provider latency. The caller's
    # shared deadline can shorten, never extend, these limits.
    limiter = account_limiter(slot, concurrency)
    remaining = min(120.0, max(0.001, deadline - monotonic())) if deadline else 120.0
    try:
        async with asyncio.timeout(remaining):
            await limiter.acquire()
    except TimeoutError:
        audit.update(
            status="unavailable",
            failure="account_queue_deadline",
            queue_wait_ms=round((monotonic() - queued) * 1000),
            provider_latency_ms=0,
            completed_at=datetime.now(UTC).isoformat(),
        )
        return audit
    try:
        started = monotonic()
        audit.update(
            queue_wait_ms=round((started - queued) * 1000), started_at=datetime.now(UTC).isoformat()
        )
        record_model_event(
            role=role,
            provider=slot.provider,
            model=slot.model,
            attempt=attempt,
            status="calling",
            failure_type=None,
            http_status=None,
            elapsed_ms=0,
            operation_kind=operation,
            call_id=call_id,
        )
        try:
            provider_timeout = (
                min(timeout, max(0.001, deadline - monotonic())) if deadline else timeout
            )
            async with asyncio.timeout(provider_timeout):
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(provider_timeout), follow_redirects=False
                ) as client:
                    response = await client.post(
                        slot.base_url.rstrip("/") + "/chat/completions",
                        json=request,
                        headers={"Authorization": "Bearer " + slot.api_key} if slot.api_key else {},
                    )
                    response.raise_for_status()
            body = response.json()
            choice = body["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") == "length":
                raise ValueError("output_token_limit")
            if not isinstance(content, str) or not content.strip() or len(content) > 131072:
                raise ValueError("invalid_completion_envelope")
            usage = body.get("usage") or {}
            audit.update(
                raw_response=content,
                finish_reason=choice.get("finish_reason"),
                http_status=response.status_code,
                status="responded",
            )
            for source, target in (
                ("prompt_tokens", "input_tokens"),
                ("completion_tokens", "output_tokens"),
            ):
                value = usage.get(source) if isinstance(usage, dict) else None
                audit[target] = value if type(value) is int and value >= 0 else None
        except asyncio.CancelledError:
            record_model_event(
                role=role,
                provider=slot.provider,
                model=slot.model,
                attempt=attempt,
                status="unavailable",
                failure_type="cancelled_or_deadline",
                http_status=None,
                elapsed_ms=round((monotonic() - started) * 1000),
                operation_kind=operation,
                call_id=call_id,
            )
            raise
        except Exception as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            category = (
                "quota_exceeded"
                if isinstance(exc, httpx.HTTPStatusError) and quota_exhausted(exc.response)
                else "provider_http_error"
                if status
                else "cancelled_or_deadline"
                if isinstance(exc, asyncio.CancelledError)
                else type(exc).__name__
            )
            audit.update(status="unavailable", failure=category, http_status=status)
            if isinstance(exc, httpx.HTTPStatusError):
                try:
                    error = exc.response.json().get("error", {})
                    if isinstance(error, dict):
                        audit["provider_error"] = {
                            key: value.replace(slot.api_key or "\x00", "[REDACTED]")[:500]
                            for key, value in error.items()
                            if key in {"message", "code", "type", "param"}
                            and isinstance(value, str)
                        }
                except (ValueError, AttributeError):
                    pass
        audit.update(
            completed_at=datetime.now(UTC).isoformat(),
            provider_latency_ms=round((monotonic() - started) * 1000),
        )
        record_model_event(
            role=role,
            provider=slot.provider,
            model=slot.model,
            attempt=attempt,
            status=audit["status"],
            failure_type=audit.get("failure"),
            http_status=audit.get("http_status"),
            elapsed_ms=audit["provider_latency_ms"],
            response_content=audit.get("raw_response"),
            operation_kind=operation,
            call_id=call_id,
            response_metadata={
                k: audit[k]
                for k in ("queue_wait_ms", "input_tokens", "output_tokens", "provider_error")
                if k in audit
            },
        )
    finally:
        limiter.release()
    return audit
