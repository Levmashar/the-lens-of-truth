"""Phase 3A grounding and vocabulary-linking behavior."""

import asyncio
import json

import httpx
import pytest

from app.adapters.claim_extractor import ExtractedClaimCandidate, MiriClaimExtractor, PicoCandidate
from app.core.errors import ExternalCapabilityError
from app.medical.linker import MedicalEntityLinker
from app.medical.mesh import LocalMeshProvider, UnconfiguredMeshProvider
from app.medical.umls import LocalUmlsProvider, UnconfiguredUmlsProvider
from app.pipeline.pico import normalization_status, normalize_pico


def _sunscreen_candidate() -> ExtractedClaimCandidate:
    source = "Frequent sunscreen use causes melanoma."
    return ExtractedClaimCandidate(
        raw_span=source,
        span_start=0,
        span_end=len(source),
        claim_type="causal",
        pico=PicoCandidate(
            intervention_or_exposure="frequent sunscreen use",
            outcome="melanoma",
        ),
    )


def test_sunscreen_pico_is_grounded_and_preserves_original_claim() -> None:
    pico = normalize_pico(_sunscreen_candidate())

    assert pico.original_claim == "Frequent sunscreen use causes melanoma."
    assert pico.population is None
    assert pico.intervention_or_exposure == "Frequent sunscreen use"
    assert pico.comparator is None
    assert pico.outcome == "melanoma"
    assert pico.timeframe is None
    assert pico.claim_type == "causal"


def test_unstated_model_pico_fields_are_dropped() -> None:
    candidate = _sunscreen_candidate().model_copy(
        update={
            "pico": PicoCandidate(
                population="children",
                intervention_or_exposure="frequent sunscreen use",
                comparator="placebo",
                outcome="melanoma",
            )
        }
    )

    pico = normalize_pico(candidate)

    assert pico.population is None
    assert pico.comparator is None


def test_missing_vocabulary_providers_leave_mentions_unresolved() -> None:
    pico = normalize_pico(_sunscreen_candidate())
    linker = MedicalEntityLinker(UnconfiguredUmlsProvider(), UnconfiguredMeshProvider())

    entities = linker.link(pico)

    assert len(entities) == 2
    assert all(entity.umls_cui is None and entity.mesh_id is None for entity in entities)
    assert normalization_status(pico, linked_count=0, mention_count=len(entities)) == "pico_only"


def test_missing_pico_entities_remain_empty_and_status_unresolved() -> None:
    candidate = ExtractedClaimCandidate(
        raw_span="A claim without usable framing.",
        span_start=0,
        span_end=31,
    )
    pico = normalize_pico(candidate)
    linker = MedicalEntityLinker(UnconfiguredUmlsProvider(), UnconfiguredMeshProvider())

    assert linker.link(pico) == ()
    assert normalization_status(pico, linked_count=0, mention_count=0) == "unresolved"


def test_low_confidence_mapping_never_assigns_identifier() -> None:
    linker = MedicalEntityLinker(
        umls=LocalUmlsProvider({"sunscreen": ("TEST_CUI", "Test Concept", 0.45)}),
        mesh=LocalMeshProvider({}),
    )

    entities = linker.link(normalize_pico(_sunscreen_candidate()))
    sunscreen = next(entity for entity in entities if entity.surface_text == "sunscreen")

    assert sunscreen.umls_cui is None
    assert sunscreen.mesh_id is None
    assert sunscreen.preferred_name is None


def test_fixture_vocabulary_links_sunscreen_without_hardcoded_mapping() -> None:
    linker = MedicalEntityLinker(
        umls=LocalUmlsProvider({"sunscreen": ("TEST_CUI", "Test Concept", 0.91)}),
        mesh=LocalMeshProvider({"sunscreen": ("TEST_MESH", "Test Concept", 0.94)}),
    )
    pico = normalize_pico(_sunscreen_candidate())

    entities = linker.link(pico)
    sunscreen = next(entity for entity in entities if entity.surface_text == "sunscreen")

    assert sunscreen.entity_type == "intervention_or_exposure"
    assert sunscreen.umls_cui == "TEST_CUI"
    assert sunscreen.mesh_id == "TEST_MESH"
    assert sunscreen.confidence == 0.91
    assert (
        normalization_status(pico, linked_count=1, mention_count=len(entities))
        == "partially_linked"
    )


def test_invalid_model_pico_json_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"claims": [{"pico": ["not an object"]}]})}}
                ]
            },
        )
    )
    monkeypatch.setattr(
        MiriClaimExtractor,
        "build_client",
        lambda self: httpx.AsyncClient(transport=transport),
    )
    adapter = MiriClaimExtractor(service_name="test", base_url="http://gateway.example/v1")

    with pytest.raises(ExternalCapabilityError) as error:
        asyncio.run(adapter.extract(text="A claim", language="en"))

    assert error.value.code == "claim_extractor_invalid_response"
