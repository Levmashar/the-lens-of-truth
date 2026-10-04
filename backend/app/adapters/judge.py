"""Provider-agnostic judge transport, with an OpenAI-shaped/Miri implementation."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from time import monotonic
from typing import Protocol
from uuid import uuid4

import httpx

from app.adapters.structured_output import (
    quota_exhausted,
    rejects_json_schema_mode,
    strict_chat_schema,
)
from app.core.debug_trace import record_model_event
from app.judging.models import JudgeDecisionV2, JudgeSlot, ProviderResponse
from app.judging.prompt import PreparedJudgeInput
from app.judging.source_units import JudgeContent, JudgeContent23

logger = logging.getLogger(__name__)
_SINGLE_JSON_FENCE = re.compile(
    r"\A\s*```(?:json)?[ \t]*\r?\n(?P<body>.*?)\r?\n```[ \t]*\s*\Z",
    re.I | re.S,
)


class ProviderFailure(Exception):
    def __init__(
        self, category: str, *, retryable: bool, provider_request_id: str | None = None,
    ) -> None:
        self.category = category
        self.retryable = retryable
        self.provider_request_id = provider_request_id
        super().__init__(category)


class JudgeProvider(Protocol):
    async def evaluate(
        self, slot: JudgeSlot, prepared: PreparedJudgeInput,
    ) -> ProviderResponse:
        """Return untrusted structured text for local schema/citation validation."""


@dataclass(frozen=True)
class OpenAICompatibleJudgeProvider:
    """HTTPX chat completion; Miri uses the same shape without JSON-mode guarantees."""

    timeout_seconds: float

    async def evaluate(
        self, slot: JudgeSlot, prepared: PreparedJudgeInput,
    ) -> ProviderResponse:
        started = monotonic()
        call_id = str(uuid4())
        debug_attempt = record_model_event(
            role=f"judge_{slot.slot}", provider=slot.provider, model=slot.model,
            attempt=0, status="calling", failure_type=None, http_status=None,
            elapsed_ms=0,
            judge_run_id=prepared.judge_run_id, call_id=call_id,
            operation_kind="judge_revision" if prepared.semantic_revision_number else "judge",
            semantic_revision_number=prepared.semantic_revision_number,
        )
        body: dict[str, object] = {
            "model": slot.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": prepared.system_prompt},
                {"role": "user", "content": prepared.user_prompt},
            ],
        }
        if prepared.input_snapshot_version == "judge-input-3.0":
            # Probe only until measured adoption gates pass; no change to V2.
            from app.judging.v3 import JudgeContentV3
            output_schema = JudgeContentV3.model_json_schema()
        elif prepared.input_snapshot_version == "judge-input-2.3":
            output_schema = JudgeContent23.model_json_schema()
        else:
            output_schema = (JudgeContent if prepared.input_snapshot_version in
                             {"judge-input-2.1", "judge-input-2.2"}
                             else JudgeDecisionV2).model_json_schema()
        if (prepared.prompt_version == "judge-2.11-compact-development-2026-10-02"
                and "RESPONSE CONTRACT: Qualitative claim." in prepared.user_prompt):
            # Schema guidance supplements the prompt; local parsing enforces it
            # even if a gateway ignores constrained output. Frozen IDs retain digits.
            for definition in output_schema.get("$defs", {}).values():
                for name, field in definition.get("properties", {}).items():
                    if name in {"text", "justification"}:
                        field["pattern"] = r"^(?:[^0-9]|S[1-8])*$"
        if slot.provider in {"openai_compatible", "paratera"} and slot.request_json_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "evidence_judge_decision", "strict": True,
                    "schema": strict_chat_schema(output_schema),
                },
            }
        headers = {"Authorization": f"Bearer {slot.api_key}"} if slot.api_key else {}
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds), follow_redirects=False,
            ) as client:
                response = await client.post(
                    f"{slot.base_url.rstrip('/')}/chat/completions", headers=headers,
                    json=body,
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            self._record(slot, started, debug_attempt, status="unavailable", failure_type="timeout",
                         prepared=prepared, call_id=call_id)
            raise ProviderFailure("timeout", retryable=True) from exc
        except asyncio.CancelledError:
            self._record(slot, started, debug_attempt, status="unavailable",
                         failure_type="cancelled_or_deadline", prepared=prepared,
                         call_id=call_id)
            raise
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            format_rejected = (slot.request_json_schema
                               and rejects_json_schema_mode(exc.response))
            category = ("response_format_unsupported" if format_rejected else
                        "quota_exceeded" if quota_exhausted(exc.response) else
                        "rate_limit" if status == 429 else "provider_error")
            self._record(
                slot, started, debug_attempt, status="unavailable", failure_type=category,
                http_status=status,
                prepared=prepared, call_id=call_id,
            )
            raise ProviderFailure(
                category, retryable=format_rejected or status == 429 or status >= 500,
                provider_request_id=_safe_id(exc.response.headers.get("x-request-id")),
            ) from exc
        except httpx.RequestError as exc:
            self._record(slot, started, debug_attempt, status="unavailable",
                         failure_type="transport", prepared=prepared, call_id=call_id)
            raise ProviderFailure("transport", retryable=True) from exc
        content: str | None = None
        try:
            payload = response.json()
            choice = payload["choices"][0]["message"]
            content = choice["content"]
            if not isinstance(content, str):
                raise ValueError("Completion content is not text")
            usage = payload.get("usage") or {}
            if not isinstance(usage, dict):
                raise ValueError("Completion usage is not an object")
            returned_model = payload.get("model")
            self._record(
                slot, started, debug_attempt, status="responded", response_content=content,
                http_status=response.status_code,
                prepared=prepared, call_id=call_id,
            )
            normalized_content = _unwrap_single_json_fence(content)
            if normalized_content is not content:
                logger.info(
                    "judge_response_transport_normalization slot=%d provider=%s model=%s "
                    "category=single_json_fence",
                    slot.slot, slot.provider, slot.model,
                )
            return ProviderResponse(
                content=normalized_content,
                input_tokens=_nonnegative_int(usage.get("prompt_tokens")),
                output_tokens=_nonnegative_int(usage.get("completion_tokens")),
                provider_request_id=_safe_id(response.headers.get("x-request-id")),
                model_snapshot=_safe_model(returned_model),
                system_fingerprint=_safe_id(payload.get("system_fingerprint")),
                response_id=_safe_id(payload.get("id")),
            )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            self._record(
                slot, started, debug_attempt, status="responded", failure_type="malformed_json",
                http_status=response.status_code, response_content=content,
                prepared=prepared, call_id=call_id,
            )
            raise ProviderFailure("malformed_json", retryable=True) from exc

    @staticmethod
    def _record(
        slot: JudgeSlot, started: float, attempt: int, *, status: str,
        failure_type: str | None = None, http_status: int | None = None,
        response_content: str | None = None,
        prepared: PreparedJudgeInput, call_id: str,
    ) -> None:
        record_model_event(
            role=f"judge_{slot.slot}", provider=slot.provider, model=slot.model,
            attempt=attempt, status=status, failure_type=failure_type,
            http_status=http_status,
            elapsed_ms=round((monotonic() - started) * 1000),
            response_content=response_content,
            judge_run_id=prepared.judge_run_id, call_id=call_id,
            operation_kind="judge_revision" if prepared.semantic_revision_number else "judge",
            semantic_revision_number=prepared.semantic_revision_number,
        )


def _nonnegative_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _unwrap_single_json_fence(content: str) -> str:
    """Remove only a whole-response Markdown wrapper around one JSON object.

    This repairs transport presentation, never schema fields or medical text.
    Prose, multiple blocks, and malformed/non-object JSON remain untouched for
    the usual strict local parser to reject.
    """

    match = _SINGLE_JSON_FENCE.fullmatch(content)
    if match is None:
        return content
    candidate = match.group("body").strip()
    try:
        decoded = json.loads(candidate)
    except ValueError:
        return content
    return candidate if isinstance(decoded, dict) else content


def _safe_id(value: object) -> str | None:
    return value if (isinstance(value, str)
                     and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value)) else None


def _safe_model(value: object) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(
        r"[A-Za-z0-9._:/-]{1,128}", value,
    ) else None
