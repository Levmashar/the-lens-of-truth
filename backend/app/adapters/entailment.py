"""Development-only, one-passage entailment check through an existing model slot.

This adapter is not an approved production validator. It sends no tools or
retrieval requests, and every response is checked against the frozen E ID.
"""

import asyncio
from dataclasses import dataclass
from time import monotonic
from uuid import uuid4

import httpx

from app.adapters.structured_output import (
    quota_exhausted,
    rejects_json_schema_mode,
    strict_chat_schema,
)
from app.core.debug_trace import record_model_event
from app.validation.entailment import PreparedEntailmentInput, parse_entailment_json
from app.validation.joint import JointResponse, check_response
from app.validation.joint23 import JointResponse23, check_response23
from app.validation.models import EntailmentOutput
from app.validation.relations import ClaimRelationResponse, parse_relation_response
from app.validation.semantic import (
    ConclusionSemanticResponse,
    PreparedSemanticInput,
    StatementSemanticResponse,
    parse_conclusion_response,
    parse_statement_response,
)


@dataclass(frozen=True)
class OpenAICompatibleEntailmentValidator:
    provider: str
    model: str
    base_url: str
    api_key: str | None
    timeout_seconds: float = 20.0

    async def assess_statement(
        self, prepared: PreparedSemanticInput,
    ) -> StatementSemanticResponse:
        content = await self._semantic_completion(prepared, StatementSemanticResponse)
        return parse_statement_response(content, prepared)

    async def assess_conclusion(
        self, prepared: PreparedSemanticInput,
    ) -> ConclusionSemanticResponse:
        content = await self._semantic_completion(prepared, ConclusionSemanticResponse)
        return parse_conclusion_response(content, prepared)

    async def assess_relations(
        self, prepared: PreparedSemanticInput,
    ) -> ClaimRelationResponse:
        content = await self._semantic_completion(prepared, ClaimRelationResponse)
        return parse_relation_response(content, prepared)

    async def assess_joint(self, prepared: PreparedSemanticInput) -> JointResponse:
        content = await self._semantic_completion(prepared, JointResponse)
        if len(content) > 32768:
            raise ValueError("Joint response exceeds bound")
        response = JointResponse.model_validate_json(content, strict=True)
        check_response(response, prepared)
        return response

    async def assess_joint23(self, prepared: PreparedSemanticInput) -> JointResponse23:
        content = await self._semantic_completion(prepared, JointResponse23)
        if len(content) > 32768:
            raise ValueError("Axes response exceeds bound")
        response = JointResponse23.model_validate_json(content, strict=True)
        check_response23(response, prepared)
        return response

    async def _semantic_completion(
        self, prepared: PreparedSemanticInput,
        schema: type[StatementSemanticResponse] | type[ConclusionSemanticResponse]
        | type[ClaimRelationResponse] | type[JointResponse] | type[JointResponse23],
    ) -> str:
        started = monotonic()
        call_id = str(uuid4())
        role = "semantic_validator"
        attempt = record_model_event(
            role=role, provider=self.provider, model=self.model, attempt=0,
            status="calling", failure_type=None, http_status=None, elapsed_ms=0,
            judge_run_id=prepared.judge_run_id,
            statement_ids=prepared.statement_ids, evidence_ids=prepared.evidence_ids,
            operation_kind=prepared.operation, call_id=call_id,
            validation_run_id=prepared.validation_run_id,
        )
        body: dict[str, object] = {
            "model": self.model, "temperature": 0,
            "messages": [
                {"role": "system", "content": prepared.system_prompt},
                {"role": "user", "content": prepared.user_prompt},
            ],
        }
        if self.provider in {"openai_compatible", "paratera"}:
            body["response_format"] = {
                "type": "json_schema", "json_schema": {
                    "name": prepared.operation, "strict": True,
                    "schema": strict_chat_schema(schema.model_json_schema()),
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
                if (prepared.operation != "joint_evidence_axes" and "response_format" in body
                        and rejects_json_schema_mode(response)):
                    record_model_event(
                        role=role, provider=self.provider, model=self.model,
                        attempt=attempt, status="retrying",
                        failure_type="response_format_unsupported",
                        http_status=response.status_code,
                        elapsed_ms=round((monotonic() - started) * 1000),
                        judge_run_id=prepared.judge_run_id,
                        statement_ids=prepared.statement_ids,
                        evidence_ids=prepared.evidence_ids,
                        operation_kind=prepared.operation, call_id=call_id,
                        validation_run_id=prepared.validation_run_id,
                    )
                    body.pop("response_format")
                    response = await client.post(
                        f"{self.base_url.rstrip('/')}/chat/completions",
                        headers=headers, json=body,
                    )
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("semantic completion content is not text")
        except asyncio.CancelledError:
            record_model_event(
                role=role, provider=self.provider, model=self.model, attempt=attempt,
                status="unavailable", failure_type="cancelled_or_deadline",
                http_status=None, elapsed_ms=round((monotonic() - started) * 1000),
                judge_run_id=prepared.judge_run_id,
                statement_ids=prepared.statement_ids, evidence_ids=prepared.evidence_ids,
                operation_kind=prepared.operation, call_id=call_id,
                validation_run_id=prepared.validation_run_id,
            )
            raise
        except Exception as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            failure = ("quota_exceeded" if isinstance(exc, httpx.HTTPStatusError)
                       and quota_exhausted(exc.response) else type(exc).__name__)
            record_model_event(
                role=role, provider=self.provider, model=self.model, attempt=attempt,
                status="unavailable", failure_type=failure,
                http_status=status, elapsed_ms=round((monotonic() - started) * 1000),
                judge_run_id=prepared.judge_run_id,
                statement_ids=prepared.statement_ids, evidence_ids=prepared.evidence_ids,
                operation_kind=prepared.operation, call_id=call_id,
                validation_run_id=prepared.validation_run_id,
            )
            raise
        record_model_event(
            role=role, provider=self.provider, model=self.model, attempt=attempt,
            status="responded", failure_type=None, http_status=response.status_code,
            elapsed_ms=round((monotonic() - started) * 1000), response_content=content,
            judge_run_id=prepared.judge_run_id,
            statement_ids=prepared.statement_ids, evidence_ids=prepared.evidence_ids,
            operation_kind=prepared.operation, call_id=call_id,
            validation_run_id=prepared.validation_run_id,
        )
        return content

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
        if self.provider in {"openai_compatible", "paratera"}:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "evidence_entailment", "strict": True,
                    "schema": strict_chat_schema(EntailmentOutput.model_json_schema()),
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
                if "response_format" in body and rejects_json_schema_mode(response):
                    record_model_event(
                        role=role, provider=self.provider, model=self.model,
                        attempt=attempt, status="retrying",
                        failure_type="response_format_unsupported",
                        http_status=response.status_code,
                        elapsed_ms=round((monotonic() - started) * 1000),
                    )
                    body.pop("response_format")
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
