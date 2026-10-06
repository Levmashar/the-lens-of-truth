"""Live-validation transport and development-only composition without live calls."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from app.adapters.entailment import OpenAICompatibleEntailmentValidator
from app.core.config import Settings
from app.core.debug_trace import model_events, trace_analysis
from app.judging.models import JudgeLabel
from app.orchestration.worker import (
    build_orchestrator,
    configured_development_validator,
    development_entailment_validator,
)
from app.validation.entailment import PreparedEntailmentInput, prepare_entailment_input
from app.validation.models import EntailmentInput, EntailmentStatus
from app.validation.semantic import prepare_semantic_input
from app.verdict.models import AggregationMode
from tests.test_validation import fixture_pack, judge_for


def _prepared() -> PreparedEntailmentInput:
    return prepare_entailment_input(EntailmentInput(
        evidence_id="E1", role="cited", exact_claim="X causes Y.",
        judge_label=JudgeLabel.NOT_ENOUGH_EVIDENCE,
        reasoning_summary="E1 shows association, not causation.",
        passage="X was associated with Y in a cohort.",
        document_title="Study", document_pmid="123", study_design="cohort",
    ))


@pytest.mark.parametrize("gateway", ["openai_compatible", "paratera"])
def test_adapter_sends_one_frozen_passage_without_tools(
    monkeypatch: pytest.MonkeyPatch, gateway: str,
) -> None:
    original_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer fixture-key"
        payload = json.loads(request.content)
        assert "tools" not in payload
        assert "search" not in payload
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["messages"][1]["content"].count("X was associated with Y") == 1
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "status": "entails_judge_use", "evidence_claim": "Association only.",
            "scope_match": "partial", "reason": "No causal test.", "evidence_id": "E1",
        })}}]})

    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    validator = OpenAICompatibleEntailmentValidator(
        provider=gateway, model="other-family", base_url="https://example.test/v1",
        api_key="fixture-key",
    )
    result = asyncio.run(validator.validate(_prepared()))
    assert result.status == EntailmentStatus.ENTAILS_JUDGE_USE


def test_adapter_rejects_wrong_frozen_evidence_id(monkeypatch: pytest.MonkeyPatch) -> None:
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps({
                    "status": "entails_judge_use", "evidence_claim": "Claim.",
                    "scope_match": "aligned", "reason": "Reason.", "evidence_id": "E99",
                })}}],
            })), **kwargs,
        ),
    )
    validator = OpenAICompatibleEntailmentValidator(
        provider="openai_compatible", model="other-family", base_url="https://example.test/v1",
        api_key=None,
    )
    with pytest.raises(ValueError, match="evidence ID mismatch"):
        asyncio.run(validator.validate(_prepared()))


def test_semantic_adapter_retries_only_explicit_format_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, object]] = []
    original_client = httpx.AsyncClient

    def respond(request: httpx.Request) -> httpx.Response:
        payload: dict[str, object] = json.loads(request.content)
        sent.append(payload)
        if "response_format" in payload:
            return httpx.Response(400, json={
                "error": {"message": "json_schema response_format is not supported"},
            })
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "statement_id": "S1", "evidence_ids": ["E1"],
            "status": "supported_by_sources", "scope_match": "exact",
            "reason": "The frozen passage supports the statement.",
        })}}]})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original_client(
            transport=httpx.MockTransport(respond), **kwargs,
        ),
    )
    validator = OpenAICompatibleEntailmentValidator(
        provider="openai_compatible", model="fixture", base_url="https://example.test/v1",
        api_key=None,
    )
    prepared = prepare_semantic_input(
        "statement_attribution", {"statement": "X and Y were measured."},
        judge_run_id="judge", validation_run_id="validation",
        statement_ids=("S1",), evidence_ids=("E1",),
    )
    result = asyncio.run(validator.assess_statement(prepared))
    assert result.status.value == "supported_by_sources"
    assert len(sent) == 2
    assert "response_format" in sent[0] and "response_format" not in sent[1]
    assert sent[0]["messages"] == sent[1]["messages"]


def test_evaluation_cross_checks_other_family_only() -> None:
    pack = fixture_pack()
    judge = judge_for(pack).model_copy(update={"model_family": "openai"})
    settings = Settings(
        _env_file=None, app_env="development",
        judge_1_provider="openai_compatible", judge_1_model="openai/test",
        judge_1_model_family="openai", judge_1_base_url="https://example.test/v1",
        judge_2_provider="openai_compatible", judge_2_model="google/test",
        judge_2_model_family="google", judge_2_base_url="https://example.test/v1",
    )
    validator = development_entailment_validator(settings, judge)
    assert validator is not None and validator.model == "google/test"
    assert build_orchestrator(settings).mode == AggregationMode.FIXTURE_OR_EVALUATION
    production = settings.model_copy(update={"app_env": "production"})
    assert development_entailment_validator(production, judge) is None
    assert build_orchestrator(production).mode == AggregationMode.PRODUCTION


def test_search_enabled_model_is_not_cross_validator() -> None:
    judge = judge_for(fixture_pack()).model_copy(update={"model_family": "openai"})
    settings = Settings(
        _env_file=None, app_env="development", judge_allow_search_enabled_development=True,
        judge_1_provider="openai_compatible", judge_1_model="openai/test",
        judge_1_model_family="openai", judge_1_base_url="https://example.test/v1",
        judge_2_provider="miri", judge_2_model="gemini-browser",
        judge_2_model_family="google", judge_2_base_url="https://example.test/v1",
    )
    assert development_entailment_validator(settings, judge) is None


def test_explicit_paratera_validator_is_independent_of_judge_three() -> None:
    judge = judge_for(fixture_pack()).model_copy(update={"model_family": "glm"})
    settings = Settings(
        _env_file=None, app_env="development",
        validator_provider="paratera", validator_model="GLM-5.2",
        validator_base_url="https://llmapi.paratera.com/v1",
        validator_api_key="fixture-key",
    )
    validator = development_entailment_validator(settings, judge)
    assert validator is not None and validator.provider == "paratera"
    assert validator.model == "GLM-5.2"
    assert configured_development_validator(settings, timeout_seconds=75).timeout_seconds == 75
    with pytest.raises(ValueError, match="Validator requires"):
        configured_development_validator(
            settings.model_copy(update={"validator_api_key": None}), timeout_seconds=75,
        )
    production = settings.model_copy(update={"app_env": "production"})
    assert development_entailment_validator(production, judge) is None


@pytest.mark.parametrize("thinking", [None, False])
def test_validator_thinking_configuration_reaches_both_transport_paths(
    monkeypatch: pytest.MonkeyPatch, thinking: bool | None,
) -> None:
    settings = Settings(
        _env_file=None, app_env="test", validator_provider="paratera",
        validator_model="Qwen3.8-Flash", validator_api_key="fixture-key",
        validator_base_url="https://example.test/v1", validator_thinking_enabled=thinking,
    )
    validator = configured_development_validator(settings, timeout_seconds=75)
    assert validator is not None
    assert validator.thinking_enabled == thinking
    original_client = httpx.AsyncClient
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["model"] == "Qwen3.8-Flash"
        assert "tools" not in body
        if len(bodies) == 1:
            result = {"statement_id": "S1", "evidence_ids": ["E1"],
                      "status": "supported_by_sources", "scope_match": "exact",
                      "reason": "The source accurately describes this finding."}
        else:
            result = {"status": "entails_judge_use", "evidence_claim": "Association only.",
                      "scope_match": "partial", "reason": "No causal test.",
                      "evidence_id": "E1"}
        return httpx.Response(200, json={"choices": [{"message": {
            "content": json.dumps(result),
        }}]})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    prepared = prepare_semantic_input(
        "statement_attribution", {"statement": "X and Y were measured."},
        judge_run_id="judge", validation_run_id="validation",
        statement_ids=("S1",), evidence_ids=("E1",),
    )
    asyncio.run(validator.assess_statement(prepared))
    asyncio.run(validator.validate(_prepared()))
    for body in bodies:
        if thinking is None:
            assert "enable_thinking" not in body
        else:
            assert body["enable_thinking"] is thinking


def test_validator_rejects_unverified_thinking_configuration_before_calling() -> None:
    with pytest.raises(ValueError, match="thinking"):
        configured_development_validator(Settings(
            _env_file=None, validator_provider="openai_compatible",
            validator_model="openai/gpt-6-luna", validator_base_url="https://example.test/v1",
            validator_api_key="fixture-key", validator_thinking_enabled=False,
        ), timeout_seconds=75)


def test_joint_transport_deadline_closes_the_calling_debug_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_client = httpx.AsyncClient

    async def waiting(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(waiting), **kwargs,
    ))
    validator = OpenAICompatibleEntailmentValidator(
        "paratera", "fixture", "https://example.test/v1", "fixture-key",
    )
    prepared = prepare_semantic_input(
        "statement_attribution", {"statement": "X and Y were measured."},
        judge_run_id="judge", validation_run_id="validation",
        statement_ids=("S1",), evidence_ids=("E1",),
    )
    identifier = uuid4()

    async def run() -> None:
        with trace_analysis(identifier, enabled=True):
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.01):
                    await validator.assess_statement(prepared)

    asyncio.run(run())
    events = model_events(identifier)
    assert events[-1]["status"] == "unavailable"
    assert events[-1]["failure_type"] == "cancelled_or_deadline"
    assert events[-1]["call_id"] == events[0]["call_id"]
