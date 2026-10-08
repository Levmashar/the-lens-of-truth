"""Ordinary grammar cannot create or hide required medical entities."""

import pytest

from app.medical.linker import MedicalEntityLinker
from app.medical.mesh import LocalMeshProvider
from app.medical.umls import UnconfiguredUmlsProvider
from app.pipeline.completeness import assess_completeness
from app.pipeline.pico import NormalizedPico, normalization_status


def linker() -> MedicalEntityLinker:
    return MedicalEntityLinker(UnconfiguredUmlsProvider(), LocalMeshProvider({
        "who": ("D014944", "World Health Organization", 0.95),
        "World Health Organization": ("D014944", "World Health Organization", 1.0),
        "sunscreen": ("D013473", "Sunscreening Agents", 0.95),
        "skin cancer": ("D012878", "Skin Neoplasms", 0.95),
        "skin cancers": ("D012878", "Skin Neoplasms", 0.95),
        "risks": ("D012306", "Risk", 0.95),
        "association": ("D001244", "Association", 1.0),
        "sunburn": ("D013471", "Sunburn", 1.0),
        "estrogen": ("D004967", "Estrogens", 0.95),
        "soy": ("D013025", "Soybeans", 0.95),
    }))


def test_relative_pronoun_and_plural_risk_do_not_block_complete_medical_framing() -> None:
    pico = NormalizedPico(
        original_claim="people who used sunscreen frequently had higher risks of skin cancers",
        population="people who used sunscreen frequently", intervention_or_exposure="sunscreen",
        outcome="skin cancers", claim_type="association",
    )
    resolver = linker()
    entities = resolver.link(pico)
    quality = assess_completeness(pico, entities, resolver.mesh)
    assert not any(entity.mesh_id == "D014944" for entity in entities)
    assert not quality.missing_explicit_concepts
    assert not quality.required_slots_missing
    assert quality.normalization_coverage == 1.0
    assert normalization_status(pico, linked_count=len(entities), mention_count=len(entities),
                                quality=quality) == "normalized"


@pytest.mark.parametrize("organization", ["WHO", "World Health Organization"])
def test_explicit_organization_name_and_uppercase_acronym_remain_linked(
    organization: str,
) -> None:
    pico = NormalizedPico(original_claim=f"{organization} recommends sunscreen.",
                          intervention_or_exposure=organization, outcome="sunscreen")
    resolver = linker()
    entities = resolver.link(pico)
    assert any(entity.mesh_id == "D014944" for entity in entities)
    assert not assess_completeness(pico, entities, resolver.mesh).missing_explicit_concepts


@pytest.mark.parametrize("pronoun", ["who", "Who"])
def test_pronoun_without_acronym_does_not_create_an_organization(pronoun: str) -> None:
    resolver = linker()
    pico = NormalizedPico(original_claim=f"{pronoun} used sunscreen?", population=pronoun)
    assert not any(entity.mesh_id == "D014944" for entity in resolver.link(pico))


@pytest.mark.parametrize("relation", ["association with", "association between"])
def test_relationship_noun_is_not_a_required_medical_concept(relation: str) -> None:
    pico = NormalizedPico(
        original_claim=f"There is an {relation} sunscreen use and skin cancer.",
        intervention_or_exposure="sunscreen use", outcome="skin cancer", claim_type="association",
    )
    resolver = linker()
    entities = resolver.link(pico)
    assert not assess_completeness(pico, entities, resolver.mesh).missing_explicit_concepts


def test_relation_word_exemption_does_not_hide_a_real_omitted_disease_detail() -> None:
    pico = NormalizedPico(
        original_claim="Sunscreen has an association with skin cancer and sunburn.",
        intervention_or_exposure="Sunscreen", outcome="skin cancer", claim_type="association",
    )
    resolver = linker()
    assert assess_completeness(pico, resolver.link(pico), resolver.mesh) \
        .missing_explicit_concepts == ("sunburn",)


def test_association_outside_relation_grammar_remains_a_required_medical_concept() -> None:
    pico = NormalizedPico(original_claim="Free association changes health.",
                          intervention_or_exposure="health")
    resolver = linker()
    assert assess_completeness(pico, resolver.link(pico), resolver.mesh) \
        .missing_explicit_concepts == ("association",)


def test_partial_word_cannot_cover_an_omitted_medical_concept() -> None:
    pico = NormalizedPico(original_claim="Soy raises estrogen.", intervention_or_exposure="Soy",
                          outcome="estrogenic effects", claim_type="causal")
    resolver = linker()
    assert assess_completeness(pico, (), resolver.mesh).missing_explicit_concepts == ("estrogen",)
