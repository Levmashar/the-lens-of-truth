"""Offline tests for official-format MeSH import, lookup, and safe re-normalization."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.medical.linker import MedicalEntityLinker
from app.medical.mesh import (
    MESH_MENTION_MAX_SOURCE_CHARACTERS,
    IndexedMeshProvider,
    LocalMeshProvider,
)
from app.medical.mesh_import import import_mesh_xml
from app.medical.renormalize import renormalize_claim, renormalize_pending
from app.medical.umls import LocalUmlsProvider, UnconfiguredUmlsProvider
from app.models.claim import Claim
from app.pipeline.completeness import assess_completeness
from app.pipeline.pico import NormalizedPico, normalization_status
from app.pipeline.readiness import ready_for_evidence


@pytest.fixture
def mesh_provider(tmp_path: Path) -> IndexedMeshProvider:
    """Small NLM-shaped descriptor XML; IDs are test fixtures, not bundled mappings."""

    source = tmp_path / "desc2026.xml"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<DescriptorRecordSet>
  <DescriptorRecord>
    <DescriptorUI>D000001</DescriptorUI>
    <DescriptorName><String>Sunscreening Agents</String></DescriptorName>
    <TreeNumberList><TreeNumber>D27.505</TreeNumber></TreeNumberList>
    <ConceptList><Concept><TermList>
      <Term><String>Sunscreening Agents</String></Term>
      <Term><String>Sunscreen</String></Term>
    </TermList></Concept></ConceptList>
  </DescriptorRecord>
  <DescriptorRecord>
    <DescriptorUI>D000002</DescriptorUI>
    <DescriptorName><String>Melanoma</String></DescriptorName>
    <TreeNumberList><TreeNumber>C04.557</TreeNumber></TreeNumberList>
    <ConceptList><Concept><TermList>
      <Term><String>Melanoma</String></Term>
      <Term><String>Malignant Melanoma</String></Term>
    </TermList></Concept></ConceptList>
  </DescriptorRecord>
  <DescriptorRecord>
    <DescriptorUI>D000003</DescriptorUI>
    <DescriptorName><String>Example One</String></DescriptorName>
    <ConceptList><Concept><TermList><Term><String>Shared Term</String></Term>
    </TermList></Concept></ConceptList>
  </DescriptorRecord>
  <DescriptorRecord>
    <DescriptorUI>D000004</DescriptorUI>
    <DescriptorName><String>Example Two</String></DescriptorName>
    <ConceptList><Concept><TermList><Term><String>Shared Term</String></Term>
    </TermList></Concept></ConceptList>
  </DescriptorRecord>
</DescriptorRecordSet>""",
        encoding="utf-8",
    )
    index = tmp_path / "mesh.sqlite3"
    assert import_mesh_xml(source_path=source, index_path=index, release="2026") == 4
    return IndexedMeshProvider(index)


def test_exact_preferred_name_and_release(mesh_provider: IndexedMeshProvider) -> None:
    match, = mesh_provider.lookup("Melanoma")
    assert match.mesh_id == "D000002"
    assert match.preferred_name == "Melanoma"
    assert match.match_type == "exact"
    assert match.confidence == 1.0
    assert match.tree_numbers == ("C04.557",)
    assert match.terminology_version == "2026"
    assert match.terminology_sha256 is not None
    assert len(match.terminology_sha256) == 64


def test_entry_term_is_synonym(mesh_provider: IndexedMeshProvider) -> None:
    match, = mesh_provider.lookup("sunscreen")
    assert match.mesh_id == "D000001"
    assert match.preferred_name == "Sunscreening Agents"
    assert match.match_type == "synonym"
    assert match.confidence == 0.95


@pytest.mark.parametrize("prefix", ["x " * 21, "context " * 40, "☀\n" + "context " * 150])
def test_late_mentions_keep_exact_unicode_offsets_and_ambiguity(
    mesh_provider: IndexedMeshProvider, prefix: str,
) -> None:
    source = prefix + "Malignant\nMelanoma and Shared Term."
    matches = mesh_provider.find_mentions(source)

    melanoma = next(match for match in matches if match.surface_text == "Malignant\nMelanoma")
    assert melanoma.start == len(prefix)
    assert melanoma.end == len(prefix) + len("Malignant\nMelanoma")
    assert source[melanoma.start:melanoma.end] == melanoma.surface_text
    assert melanoma.mesh_id == "D000002"
    assert melanoma.match_type == "synonym"
    assert melanoma.terminology_version == "2026"
    assert melanoma.terminology_sha256 == mesh_provider.source_sha256
    assert melanoma.tree_numbers == ("C04.557",)
    ambiguous = [match for match in matches if match.surface_text == "Shared Term"]
    assert {match.mesh_id for match in ambiguous} == {"D000003", "D000004"}
    assert all(source[match.start:match.end] == match.surface_text for match in matches)


def test_long_scan_batches_queries_below_sqlite_parameter_limit(
    mesh_provider: IndexedMeshProvider, monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect = mesh_provider._connect

    def limited_connection() -> sqlite3.Connection:
        connection = connect()
        connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 500)
        return connection

    monkeypatch.setattr(mesh_provider, "_connect", limited_connection)
    # More than 500 distinct subphrases must not become a single SQL request.
    source = " ".join(f"context{index}" for index in range(150)) + " Melanoma"
    match, = mesh_provider.find_mentions(source)
    assert match.surface_text == "Melanoma"
    assert match.start == source.index("Melanoma")


def test_scan_covers_the_entire_publicly_accepted_source(
    mesh_provider: IndexedMeshProvider,
) -> None:
    source = "context " * 2499 + "Melanoma"
    assert len(source) == MESH_MENTION_MAX_SOURCE_CHARACTERS
    match, = mesh_provider.find_mentions(source)
    assert match.end == len(source)
    assert match.surface_text == source[match.start:match.end] == "Melanoma"
    pico = NormalizedPico(original_claim=source, outcome="Melanoma")
    entities = MedicalEntityLinker(UnconfiguredUmlsProvider(), mesh_provider).link(pico)
    quality = assess_completeness(pico, entities, mesh_provider)
    assert "source_terminology_scan_truncated" not in quality.normalization_warnings


def test_long_complete_claim_can_proceed_but_missing_late_concept_cannot(
    mesh_provider: IndexedMeshProvider,
) -> None:
    source = "Sunscreen " + "context " * 40 + "causes Melanoma."
    assert len(source) > 256
    pico = NormalizedPico(
        original_claim=source, intervention_or_exposure="Sunscreen",
        outcome="Melanoma", claim_type="causal",
    )
    linker = MedicalEntityLinker(UnconfiguredUmlsProvider(), mesh_provider)
    entities = linker.link(pico)
    quality = assess_completeness(pico, entities, mesh_provider)
    status = normalization_status(
        pico, linked_count=2, mention_count=len(entities), quality=quality,
    )
    assert status == "normalized"
    assert not quality.missing_explicit_concepts
    assert "source_terminology_scan_truncated" not in quality.normalization_warnings
    assert ready_for_evidence(
        status, pico_json=pico.model_dump(), quality_json=quality.model_dump(),
        standalone_status="complete", standalone_text=source,
    )

    omitted = pico.model_copy(update={"original_claim": source + " Shared Term."})
    omitted_quality = assess_completeness(omitted, entities, mesh_provider)
    assert omitted_quality.missing_explicit_concepts == ("Shared Term",)
    omitted_status = normalization_status(
        omitted, linked_count=2, mention_count=len(entities), quality=omitted_quality,
    )
    assert omitted_status == "partial"
    assert not ready_for_evidence(
        omitted_status, pico_json=omitted.model_dump(), quality_json=omitted_quality.model_dump(),
    )


def test_actual_source_truncation_stays_incomplete_and_never_matches_partial_token(
    mesh_provider: IndexedMeshProvider,
) -> None:
    source = " " * (MESH_MENTION_MAX_SOURCE_CHARACTERS - len("Melanoma")) + "MelanomaFake"
    assert len(source) > MESH_MENTION_MAX_SOURCE_CHARACTERS
    assert mesh_provider.find_mentions(source) == ()
    pico = NormalizedPico(original_claim=source, outcome="MelanomaFake")
    quality = assess_completeness(pico, (), mesh_provider)
    assert "source_terminology_scan_truncated" in quality.normalization_warnings
    status = normalization_status(pico, linked_count=1, mention_count=1, quality=quality)
    assert status == "partial"
    assert not ready_for_evidence(
        status, pico_json=pico.model_dump(), quality_json=quality.model_dump(),
    )


def test_ambiguous_alias_is_not_forced(mesh_provider: IndexedMeshProvider) -> None:
    linker = MedicalEntityLinker(UnconfiguredUmlsProvider(), mesh_provider)
    entities = linker.link(NormalizedPico(
        original_claim="Shared Term is studied.", outcome="Shared Term"
    ))
    entity, = entities
    assert entity.surface_text == "Shared Term"
    assert entity.ambiguous is True
    assert entity.mesh_id is None
    assert len(entity.candidates) == 2
    assert {candidate.mesh_id for candidate in entity.candidates} == {"D000003", "D000004"}


def test_unresolved_and_fuzzy_suggestion(mesh_provider: IndexedMeshProvider) -> None:
    assert mesh_provider.lookup("not a medical term") == ()
    assert mesh_provider.candidates("not a medical term") == ()
    fuzzy, = mesh_provider.candidates("Melanma")
    assert fuzzy.match_type == "fuzzy"
    assert fuzzy.confidence < 0.8
    linker = MedicalEntityLinker(UnconfiguredUmlsProvider(), mesh_provider)
    entity, = linker.link(NormalizedPico(original_claim="Melanma", outcome="Melanma"))
    assert entity.mesh_id is None
    assert entity.match_type == "fuzzy"
    assert entity.terminology_version == "2026"
    assert entity.candidates[0].mesh_id == "D000002"


def test_sunscreen_melanoma_without_umls_credentials(
    mesh_provider: IndexedMeshProvider,
) -> None:
    linker = MedicalEntityLinker(UnconfiguredUmlsProvider(), mesh_provider)
    entities = linker.link(NormalizedPico(
        original_claim="Frequent sunscreen use causes invasive melanoma.",
        intervention_or_exposure="sunscreen use", outcome="invasive melanoma",
    ))
    by_surface = {entity.surface_text: entity for entity in entities}
    assert by_surface["sunscreen"].mesh_id == "D000001"
    assert by_surface["sunscreen"].umls_cui is None
    assert by_surface["sunscreen"].terminology_source == "mesh"
    assert by_surface["sunscreen"].terminology_version == "2026"
    assert by_surface["sunscreen"].terminology_sha256 is not None
    assert by_surface["melanoma"].mesh_id == "D000002"
    assert by_surface["melanoma"].entity_type == "outcome"


def test_disagreeing_or_weak_optional_provider_cannot_erase_mesh() -> None:
    linker = MedicalEntityLinker(
        umls=LocalUmlsProvider({"sunscreen": ("TEST_CUI", "Different Concept", 0.95)}),
        mesh=LocalMeshProvider({"sunscreen": ("TEST_MESH", "Sunscreening Agents", 0.95)}),
    )
    entity, = linker.link(NormalizedPico(original_claim="sunscreen", outcome="sunscreen"))
    assert entity.mesh_id == "TEST_MESH"
    assert entity.umls_cui is None

    weak = MedicalEntityLinker(
        umls=UnconfiguredUmlsProvider(),
        mesh=LocalMeshProvider({"sunscreen": ("TEST_MESH", "Sunscreening Agents", 0.5)}),
    )
    weak_entity, = weak.link(NormalizedPico(original_claim="sunscreen", outcome="sunscreen"))
    assert weak_entity.mesh_id is None
    assert weak_entity.candidates[0].mesh_id == "TEST_MESH"


def test_pending_renormalization_is_idempotent_and_preserves_review(
    mesh_provider: IndexedMeshProvider,
) -> None:
    linker = MedicalEntityLinker(UnconfiguredUmlsProvider(), mesh_provider)
    claim = Claim(
        raw_text="Sunscreen causes melanoma.", claim_type="causal",
        intervention_or_exposure="Sunscreen", outcome="melanoma",
        normalization_status="pending", risk_class="standard", ordinal=1,
    )
    assert renormalize_claim(claim, linker) is True
    assert claim.normalization_status == "normalized"
    assert claim.linked_entities is not None
    assert claim.linked_entities[0]["terminology_version"] == "2026"
    assert claim.linked_entities[0]["terminology_source"] == "mesh"
    assert claim.normalization_quality is not None
    assert claim.normalization_quality["terminology_version"] == "2026"
    assert len(str(claim.normalization_quality["terminology_sha256"])) == 64
    first = claim.linked_entities.copy()
    assert renormalize_claim(claim, linker) is False
    assert claim.linked_entities == first

    reviewed = Claim(
        raw_text="Sunscreen causes melanoma.", normalization_status="pending",
        linked_entities=[{"surface_text": "Sunscreen", "mesh_id": "REVIEWED"}],
        risk_class="standard", ordinal=2,
    )
    assert renormalize_claim(reviewed, linker) is False
    assert reviewed.linked_entities[0]["mesh_id"] == "REVIEWED"


def test_pending_batch_dry_run_never_commits(mesh_provider: IndexedMeshProvider) -> None:
    claim = Claim(
        id=uuid4(), raw_text="Sunscreen causes melanoma.", claim_type="causal",
        intervention_or_exposure="Sunscreen", outcome="melanoma",
        normalization_status="pending", risk_class="standard", ordinal=1,
    )
    session = MagicMock(spec=Session)
    session.scalars.side_effect = [[claim], []]
    counts = renormalize_pending(
        session=session,
        linker=MedicalEntityLinker(UnconfiguredUmlsProvider(), mesh_provider),
        batch_size=1,
        dry_run=True,
    )
    assert (counts.updated, counts.skipped, counts.failed) == (1, 0, 0)
    session.rollback.assert_called_once()
    session.commit.assert_not_called()
