"""Development-only, one-passage entailment check through an existing model slot.

This adapter is not an approved production validator. It sends no tools or
retrieval requests, and every response is checked against the frozen E ID.
"""

from dataclasses import dataclass
from time import monotonic

import httpx

from app.core.debug_trace import record_model_event
from app.validation.entailment import PreparedEntailmentInput, parse_entailment_json
from app.validation.models import EntailmentOutput


@dataclass(frozen=True)
class OpenAICompatibleEntailmentValidator:
    provider: str
    model: str
    base_url: str
    api_key: str | None
    timeout_seconds: float = 20.0

    async def validate(self, prepared: PreparedEntailmentInput) -> EntailmentOutput:
        started = monotonic()
        role = "citation_validator"
        attempt = record_model_event(
            role=role, provider=self.provider, model=self.model, attempt=0,
            status="calling", failure_type=None, http_status=None, elapsed_ms=0,
        )
        body: dict[str, object] = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": prepared.system_prompt},
                {"role": "user", "content": prepared.user_prompt},
            ],
        }
        if self.provider == "openai_compatible":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "evidence_entailment", "strict": True,
                    "schema": EntailmentOutput.model_json_schema(),
                },
            }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds), follow_redirects=False,
            ) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers=headers, json=body,
                )
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("entailment content is not text")
            result = parse_entailment_json(content, prepared.evidence_id)
        except Exception as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            record_model_event(
                role=role, provider=self.provider, model=self.model, attempt=attempt,
                status="unavailable", failure_type=type(exc).__name__,
                http_status=status, elapsed_ms=round((monotonic() - started) * 1000),
            )
            raise
        record_model_event(
            role=role, provider=self.provider, model=self.model, attempt=attempt,
            status="responded", failure_type=None, http_status=response.status_code,
            elapsed_ms=round((monotonic() - started) * 1000), response_content=content,
        )
        return result
