import asyncio
import json
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy.orm import Session

from app.adapters.claim_extractor import (
    ClaimExtractionPayload,
    ExtractedClaimCandidate,
    MiriClaimExtractor,
    PicoCandidate,
    validate_claim_candidates,
)
from app.core.config import Settings
from app.core.errors import ExternalCapabilityError
from app.dependencies import get_claim_extractor
from app.schemas.analysis import CreateAnalysisRequest
from app.services.analysis_ingestion import AnalysisIngestionService
from app.services.redaction import PiiRedactor


def test_validated_claims_keep_exact_source_offsets() -> None:
    source = "Vitamin C prevents colds."
    payload = ClaimExtractionPayload(
        claims=[
            ExtractedClaimCandidate(
                raw_span="Vitamin C prevents colds.",
                span_start=0,
                span_end=len(source),
                normalized_claim="Vitamin C prevents common colds.",
                claim_type="preventive",
                verifiability=0.9,
                resolved_from_span_start=0,
                resolved_from_span_end=9,
            )
        ]
    )

    claims = validate_claim_candidates(payload=payload, source_text=source, maximum_claims=20)

    assert claims[0].raw_span == source[claims[0].span_start : claims[0].span_end]
    assert (
        source[claims[0].resolved_from_span_start : claims[0].resolved_from_span_end] == "Vitamin C"
    )


def test_claims_with_provider_invented_offsets_are_rejected() -> None:
    payload = ClaimExtractionPayload(
        claims=[ExtractedClaimCandidate(raw_span="Different", span_start=0, span_end=9)]
    )

    with pytest.raises(ExternalCapabilityError, match="spans"):
        validate_claim_candidates(payload=payload, source_text="Source text", maximum_claims=20)


def test_miri_adapter_requests_chatgpt_auto_and_parses_fenced_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "Vitamin C prevents colds."
    captured: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        payload = {
            "claims": [
                {
                    "raw_span": source,
                    "span_start": 0,
                    "span_end": len(source),
                    "verifiability": "externally_verifiable",
                    "pico": {
                        "population": None,
                        "intervention_or_exposure": "Vitamin C",
                        "comparator": None,
                        "outcome": "colds",
                        "timeframe": None,
                    },
                }
            ]
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": f"```json\n{json.dumps(payload)}\n```"}}]},
        )

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        MiriClaimExtractor,
        "build_client",
        lambda self: httpx.AsyncClient(transport=transport),
    )
    adapter = MiriClaimExtractor(
        service_name="miri_chatgpt_claim_extractor",
        base_url="http://gateway.example/secret/v1",
        model="chatgpt-auto",
    )

    result = asyncio.run(adapter.extract(text=source, language="en"))

    assert result.claims[0].pico is not None
    assert result.claims[0].pico.outcome == "colds"
    assert result.claims[0].verifiability is None
    assert str(captured[0].url) == "http://gateway.example/secret/v1/chat/completions"
    sent = json.loads(captured[0].content)
    assert sent["model"] == "chatgpt-auto"
    assert "response_format" not in sent
    assert "authorization" not in captured[0].headers
    assert source in sent["messages"][1]["content"]


def test_miri_adapter_rejects_non_json_browser_response(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"choices": [{"message": {"content": "I cannot answer."}}]}
        )
    )
    monkeypatch.setattr(
        MiriClaimExtractor,
        "build_client",
        lambda self: httpx.AsyncClient(transport=transport),
    )
    adapter = MiriClaimExtractor(service_name="miri", base_url="http://gateway.example/v1")

    with pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text="A claim", language="en"))

    assert error.value.code == "claim_extractor_invalid_response"
    assert error.value.status_code == 502


def test_miri_adapter_uses_optional_bearer_key(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"claims":[]}'}}]})

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        MiriClaimExtractor,
        "build_client",
        lambda self: httpx.AsyncClient(transport=transport),
    )
    adapter = MiriClaimExtractor(
        service_name="miri", base_url="http://gateway.example/v1", api_key="secret-token"
    )

    assert asyncio.run(adapter.extract(text="No health claim", language="en")).claims == []
    assert captured[0].headers["authorization"] == "Bearer secret-token"


def test_miri_configuration_defaults_to_chatgpt_auto() -> None:
    settings = Settings(
        app_env="test",
        claim_extractor_base_url="http://gateway.example/v1",
    )

    adapter = get_claim_extractor(settings)

    assert isinstance(adapter, MiriClaimExtractor)
    assert adapter.model_id == "chatgpt-auto"
    assert adapter.timeout_seconds == 180


def test_miri_without_address_fails_closed() -> None:
    adapter = get_claim_extractor(
        Settings(app_env="test", claim_extractor_provider="miri", claim_extractor_base_url=None)
    )

    with pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text="Vitamin C prevents colds.", language="en"))

    assert error.value.code == "claim_extractor_unavailable"


def test_pico_fields_are_redacted_before_persistence() -> None:
    service = AnalysisIngestionService(
        storage=Mock(),
        ocr=Mock(),
        extractor=Mock(service_name="miri", model_id="chatgpt-auto"),
        redactor=PiiRedactor(),
        retention_hours=24,
        maximum_claims=20,
        upload_max_bytes=100,
        upload_max_pixels=100,
    )
    request = CreateAnalysisRequest.model_validate(
        {
            "input": {"type": "text", "text": "Vitamin C prevents colds."},
            "consent": {"privacy_notice_version": "2026-09-01", "accepted": True},
        }
    )
    payload = ClaimExtractionPayload(
        claims=[
            ExtractedClaimCandidate(
                raw_span="Vitamin C prevents colds.",
                span_start=0,
                span_end=25,
                pico=PicoCandidate(
                    intervention_or_exposure="Vitamin C",
                    outcome="colds",
                    population="Patient SSN 123-45-6789",
                ),
            )
        ]
    )
    session = Mock(spec=Session)

    submission = service._persist_submission(
        session=session,
        request=request,
        content_sha256="a" * 64,
        candidates=payload,
        redacted_text="Vitamin C prevents colds.",
    )

    assert submission.claims[0].intervention_or_exposure == "Vitamin C"
    assert submission.claims[0].outcome == "colds"
    assert "123-45-6789" not in submission.claims[0].population
