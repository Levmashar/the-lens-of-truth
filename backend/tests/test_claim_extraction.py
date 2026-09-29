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
from app.medical.linker import MedicalEntityLinker
from app.medical.mesh import LocalMeshProvider
from app.medical.umls import UnconfiguredUmlsProvider
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
                claim_type="prevention",
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


def test_adapter_retries_invalid_source_offsets_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "Regular soy consumption lowers muscle gain."
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        claim = {
            "raw_span": source,
            "span_start": 1 if len(requests) == 1 else 0,
            "span_end": len(source),
            "claim_type": "causal",
            "pico": {
                "intervention_or_exposure": "Regular soy consumption",
                "outcome": "muscle gain",
            },
        }
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"claims": [claim]})}}]},
        )

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        MiriClaimExtractor, "build_client", lambda self: httpx.AsyncClient(transport=transport)
    )
    adapter = MiriClaimExtractor(service_name="fixture", base_url="http://gateway.example/v1")

    result = asyncio.run(adapter.extract(text=source, language="en"))

    assert len(requests) == 2
    assert result.claims[0].span_start == 0
    assert result.claims[0].raw_span == source


def test_exhausted_source_offset_repair_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "Vitamin C prevents colds."
    response = httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
        "claims": [{"raw_span": source, "span_start": 1, "span_end": len(source)}]
    })}}]})
    transport = httpx.MockTransport(lambda request: response)
    monkeypatch.setattr(
        MiriClaimExtractor, "build_client", lambda self: httpx.AsyncClient(transport=transport)
    )
    adapter = MiriClaimExtractor(service_name="fixture", base_url="http://gateway.example/v1")

    with pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text=source, language="en"))

    assert error.value.code == "claim_extractor_invalid_response"


def test_explicit_outcome_omission_gets_one_repair_then_remains_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "Regular usage of soy increases estrogen levels in body."
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        claim = {
            "raw_span": source,
            "span_start": 0,
            "span_end": len(source),
            "claim_type": "causal",
            "pico": {
                "intervention_or_exposure": "Regular usage of soy",
                "outcome": "estrogen levels in body" if len(requests) == 2 else None,
            },
        }
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"claims": [claim]})}}]},
        )

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        MiriClaimExtractor, "build_client", lambda self: httpx.AsyncClient(transport=transport)
    )
    adapter = MiriClaimExtractor(service_name="fixture", base_url="http://gateway.example/v1")

    result = asyncio.run(adapter.extract(text=source, language="en"))

    assert len(requests) == 2
    assert result.claims[0].pico is not None
    assert result.claims[0].pico.outcome == "estrogen levels in body"


def test_unrepaired_explicit_outcome_is_not_fabricated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "Vitamin C prevents the common cold."
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        claim = {
            "raw_span": source, "span_start": 0, "span_end": len(source),
            "claim_type": "prevention",
            "pico": {"intervention_or_exposure": "Vitamin C", "outcome": None},
        }
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"claims": [claim]})}}]},
        )

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        MiriClaimExtractor, "build_client", lambda self: httpx.AsyncClient(transport=transport)
    )
    adapter = MiriClaimExtractor(service_name="fixture", base_url="http://gateway.example/v1")

    result = asyncio.run(adapter.extract(text=source, language="en"))

    assert calls == 2
    assert result.claims[0].pico is not None
    assert result.claims[0].pico.outcome is None


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
    assert adapter.timeout_seconds == 55
    assert adapter.total_timeout_seconds == 115


def test_miri_without_address_fails_closed() -> None:
    adapter = get_claim_extractor(
        Settings(app_env="test", claim_extractor_provider="miri", claim_extractor_base_url=None)
    )

    with pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text="Vitamin C prevents colds.", language="en"))

    assert error.value.code == "claim_extractor_unavailable"


def test_unstated_pico_fields_are_not_persisted() -> None:
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
    assert submission.claims[0].population is None
    assert submission.claims[0].normalization_status == "pico_only"
    assert submission.claims[0].pico_json["original_claim"] == "Vitamin C prevents colds."
    assert submission.claims[0].linked_entities[0]["umls_cui"] is None


def test_exact_soy_sentence_persists_two_retrievable_partially_linked_claims() -> None:
    source = "Regular usage of soy increases estrogen levels in body, and lowers muscle gain"
    service = AnalysisIngestionService(
        storage=Mock(), ocr=Mock(), extractor=Mock(service_name="fixture", model_id="fixture"),
        redactor=PiiRedactor(), retention_hours=24, maximum_claims=20,
        upload_max_bytes=100, upload_max_pixels=100,
        entity_linker=MedicalEntityLinker(
            umls=UnconfiguredUmlsProvider(),
            mesh=LocalMeshProvider({
                "estrogen": ("D004967", "Estrogens", 0.95),
                "muscle": ("D009132", "Muscles", 0.95),
            }),
        ),
    )
    request = CreateAnalysisRequest.model_validate({
        "input": {"type": "text", "text": source},
        "consent": {"privacy_notice_version": "2026-09-01", "accepted": True},
    })
    payload = ClaimExtractionPayload(claims=[
        ExtractedClaimCandidate(
            raw_span=source[:54], span_start=0, span_end=54, claim_type="causal",
            pico=PicoCandidate(
                intervention_or_exposure="Regular usage of soy",
                outcome="estrogen levels in body",
            ),
        ),
        ExtractedClaimCandidate(
            raw_span=source[60:], span_start=60, span_end=len(source),
            claim_type="causal", coreference_uncertain=True,
            resolved_from_span_start=0, resolved_from_span_end=54,
            pico=PicoCandidate(outcome="muscle gain"),
        ),
    ])

    submission = service._persist_submission(
        session=Mock(spec=Session), request=request, content_sha256="a" * 64,
        candidates=payload, redacted_text=source,
    )

    assert len(submission.claims) == 2
    assert [claim.normalization_status for claim in submission.claims] == [
        "partially_linked", "partially_linked",
    ]
    assert [claim.outcome for claim in submission.claims] == [
        "estrogen levels in body", "muscle gain",
    ]
    assert submission.claims[1].intervention_or_exposure == "Regular usage of soy"
    assert submission.claims[1].raw_text == "lowers muscle gain"
    assert submission.claims[1].coreference_uncertain is False
    assert submission.claims[1].standalone_status == "reconstructed"
    assert submission.claims[1].normalized_text == (
        "Regular usage of soy lowers muscle gain."
    )
    assert submission.claims[0].linked_entities[0]["mesh_id"] is None
    assert submission.claims[1].linked_entities[0]["mesh_id"] is None
