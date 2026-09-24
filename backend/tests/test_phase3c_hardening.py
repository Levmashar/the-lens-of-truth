"""Offline safety regressions for claim semantics, completeness, and retries."""

import asyncio
import json
import logging

import httpx
import pytest

from app.adapters.claim_extractor import (
    ExtractedClaimCandidate,
    MiriClaimExtractor,
    OpenAICompatibleClaimExtractor,
    PicoCandidate,
)
from app.core.errors import ExternalCapabilityError
from app.medical.linker import MedicalEntityLinker
from app.medical.mesh import LocalMeshProvider
from app.medical.umls import UnconfiguredUmlsProvider
from app.pipeline.completeness import assess_completeness
from app.pipeline.pico import normalization_status, normalize_pico


def _linker() -> MedicalEntityLinker:
    return MedicalEntityLinker(
        UnconfiguredUmlsProvider(),
        LocalMeshProvider({
            "Vitamin C": ("D001205", "Ascorbic Acid", 0.95),
            "common cold": ("D003139", "Common Cold", 1.0),
            "high blood pressure": ("D006973", "Hypertension", 0.95),
            "stroke": ("D020521", "Stroke", 1.0),
            "cold": ("D003080", "Cold Temperature", 0.95),
            "melanoma": ("D008545", "Melanoma", 1.0),
            "sunscreen": ("D013473", "Sunscreening Agents", 0.95),
        }),
    )


def _candidate(
    source: str, claim_type: str, intervention: str | None, outcome: str | None,
) -> ExtractedClaimCandidate:
    return ExtractedClaimCandidate.model_validate({
        "raw_span": source, "span_start": 0, "span_end": len(source),
        "claim_type": claim_type,
        "pico": PicoCandidate(
            intervention_or_exposure=intervention, outcome=outcome
        ).model_dump(),
    })


def _status(candidate: ExtractedClaimCandidate) -> tuple[str, object]:
    pico = normalize_pico(candidate)
    linker = _linker()
    entities = linker.link(pico)
    quality = assess_completeness(pico, entities, linker.mesh)
    linked = sum(entity.mesh_id is not None for entity in entities)
    return normalization_status(
        pico, linked_count=linked, mention_count=len(entities), quality=quality
    ), quality


def test_explicit_causal_and_association_wording_cannot_be_swapped() -> None:
    causal = _candidate(
        "Frequent sunscreen use causes invasive melanoma.", "association",
        "Frequent sunscreen use", "invasive melanoma",
    )
    association = _candidate(
        "Frequent sunscreen use is associated with higher melanoma risk.", "causal",
        "Frequent sunscreen use", "higher melanoma risk",
    )
    linked = _candidate("Sunscreen was linked to melanoma.", "causal", "Sunscreen", "melanoma")

    assert causal.claim_type == "causal"
    assert normalize_pico(causal).claim_type == "causal"
    assert association.claim_type == "association"
    assert normalize_pico(association).claim_type == "association"
    assert linked.claim_type == "association"


def test_conflicting_model_paraphrase_is_discarded() -> None:
    candidate = ExtractedClaimCandidate(
        raw_span="Sunscreen is associated with melanoma.",
        span_start=0, span_end=38,
        claim_type="causal",
        normalized_claim="Sunscreen causes melanoma.",
    )
    assert candidate.claim_type == "association"
    assert candidate.normalized_claim is None


def test_vitamin_c_outcome_and_missing_outcome_regression() -> None:
    source = "Vitamin C prevents the common cold."
    complete = _candidate(source, "prevention", "Vitamin C", "common cold")
    pico = normalize_pico(complete)
    entities = _linker().link(pico)

    assert pico.outcome == "common cold"
    assert {entity.mesh_id for entity in entities} == {"D001205", "D003139"}
    assert _status(complete)[0] == "normalized"

    omitted = _candidate(source, "prevention", "Vitamin C", None)
    status, quality = _status(omitted)
    assert status == "partial"
    assert quality.missing_explicit_concepts == ("common cold",)
    assert quality.required_slots_missing == ("outcome",)
    assert quality.normalization_coverage == 0.5


def test_hypertension_synonym_and_risk_outcome_remain_grounded() -> None:
    candidate = _candidate(
        "High blood pressure increases stroke risk.", "association",
        "High blood pressure", "stroke risk",
    )
    pico = normalize_pico(candidate)
    entities = _linker().link(pico)
    assert pico.outcome == "stroke risk"
    assert {entity.mesh_id for entity in entities} == {"D006973", "D020521"}
    assert _status(candidate)[0] == "normalized"


def test_cold_and_unknown_substance_are_not_fabricated() -> None:
    cold = _candidate("Cold exposure causes illness.", "causal", "Cold exposure", "illness")
    cold_entities = _linker().link(normalize_pico(cold))
    assert all(entity.mesh_id != "D003139" for entity in cold_entities)
    illness = next(entity for entity in cold_entities if entity.surface_text == "illness")
    assert illness.mesh_id is None

    unknown = _candidate(
        "Xylophrenium prevents melanoma.", "prevention", "Xylophrenium", "melanoma"
    )
    entities = _linker().link(normalize_pico(unknown))
    assert entities[0].mesh_id is None and entities[0].umls_cui is None
    assert entities[1].mesh_id == "D008545"
    assert _status(unknown)[0] == "partially_linked"


def _adapter(monkeypatch: pytest.MonkeyPatch, responses: list[object]) -> MiriClaimExtractor:
    def respond(request: httpx.Request) -> httpx.Response:
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        assert isinstance(item, httpx.Response)
        return item

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        MiriClaimExtractor, "build_client", lambda self: httpx.AsyncClient(transport=transport)
    )
    return MiriClaimExtractor(service_name="fixture", base_url="http://gateway.example/v1")


def _reply(content: object) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_malformed_json_retries_once_without_echoing_bad_answer(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    requests: list[httpx.Request] = []
    replies = [_reply("invalid answer"), _reply('{"claims":[]}')]

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return replies.pop(0)

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        MiriClaimExtractor, "build_client", lambda self: httpx.AsyncClient(transport=transport)
    )
    adapter = MiriClaimExtractor(service_name="fixture", base_url="http://gateway.example/v1")
    with caplog.at_level(logging.INFO):
        result = asyncio.run(adapter.extract(text="Vitamin C prevents colds.", language="en"))
    assert result.claims == []
    assert len(requests) == 2
    second = json.loads(requests[1].content)
    assert "invalid answer" not in json.dumps(second)
    assert "previous response could not be parsed" in second["messages"][0]["content"]
    assert "failure_type=invalid_json" in caplog.text
    assert "attempt_count=2" in caplog.text


@pytest.mark.parametrize(
    ("responses", "failure_type"),
    [
        ([_reply("not json"), _reply("still not json")], "invalid_json"),
        ([_reply(""), _reply("  ")], "empty_response"),
        ([_reply([]), _reply([])], "unsupported_structured_response"),
        ([_reply('{"claims":[{"claim_type":"made_up"}]}')] * 2,
         "schema_validation_failure"),
    ],
)
def test_bad_responses_fail_closed_after_bounded_retry(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    responses: list[object], failure_type: str,
) -> None:
    adapter = _adapter(monkeypatch, responses)
    with caplog.at_level(logging.WARNING), pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text="A claim", language="en"))
    assert error.value.code == "claim_extractor_invalid_response"
    assert failure_type in caplog.text
    assert "attempt_count=2" in caplog.text
    assert responses == []


def test_timeout_retries_once_and_never_returns_fake_claims(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    timeout = httpx.ReadTimeout("fixture timeout")
    adapter = _adapter(monkeypatch, [timeout, timeout])
    with caplog.at_level(logging.WARNING), pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text="A claim", language="en"))
    assert error.value.code == "claim_extractor_timeout"
    assert error.value.status_code == 504
    assert "failure_type=attempt_timeout" in caplog.text
    assert "attempt_count=2" in caplog.text


def test_generic_openai_adapter_retries_temporary_provider_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503, headers={"x-request-id": "upstream-123"})
        return _reply('{"claims":[]}')

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        OpenAICompatibleClaimExtractor,
        "build_client",
        lambda self: httpx.AsyncClient(transport=transport),
    )
    adapter = OpenAICompatibleClaimExtractor(
        service_name="structured", base_url="http://gateway.example/v1",
        model="pinned-test", api_key="test-only",
    )
    with caplog.at_level(logging.INFO):
        result = asyncio.run(adapter.extract(text="No claim", language="en"))
    assert result.claims == []
    assert len(requests) == 2
    assert "response_format" in json.loads(requests[0].content)
    assert "failure_type=provider_error" in caplog.text
    assert "trace_id=upstream-123" in caplog.text
    assert "test-only" not in caplog.text
