"""Provider-agnostic judge transport, with an OpenAI-shaped/Miri implementation."""

import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.judging.models import JudgeDecision, JudgeSlot, ProviderResponse
from app.judging.prompt import PreparedJudgeInput


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
        body: dict[str, object] = {
            "model": slot.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": prepared.system_prompt},
                {"role": "user", "content": prepared.user_prompt},
            ],
        }
        if slot.provider == "openai_compatible":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "evidence_judge_decision", "strict": True,
                    "schema": JudgeDecision.model_json_schema(),
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
            raise ProviderFailure("timeout", retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            category = "rate_limit" if status == 429 else "provider_error"
            raise ProviderFailure(
                category, retryable=status == 429 or status >= 500,
                provider_request_id=_safe_id(exc.response.headers.get("x-request-id")),
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderFailure("transport", retryable=True) from exc
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
            return ProviderResponse(
                content=content,
                input_tokens=_nonnegative_int(usage.get("prompt_tokens")),
                output_tokens=_nonnegative_int(usage.get("completion_tokens")),
                provider_request_id=_safe_id(response.headers.get("x-request-id")),
                model_snapshot=_safe_model(returned_model),
            )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderFailure("malformed_json", retryable=True) from exc


def _nonnegative_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _safe_id(value: str | None) -> str | None:
    return value if value and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) else None


def _safe_model(value: object) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(
        r"[A-Za-z0-9._:/-]{1,128}", value,
    ) else None
