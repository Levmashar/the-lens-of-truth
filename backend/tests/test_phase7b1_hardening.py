"""Offline self-containment and endpoint-focused selection regressions."""

import hashlib
import re
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.adapters.claim_extractor import (
    ClaimExtractionPayload,
    ExtractedClaimCandidate,
    PicoCandidate,
    validate_claim_candidates,
)
from app.pipeline.pico import normalize_pico
from app.pipeline.readiness import ready_for_evidence
from app.retrieval.evidence_pack import build_evidence_pack, canonical_pack_bytes
from app.retrieval.models import AbstractSection, ClaimSnapshot, EvidencePack, PubMedDocument
from app.retrieval.passages import extract_passages
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import rank_passages
from app.retrieval.study_quality import annotate_study_quality

_NOW = datetime(2026, 9, 29, tzinfo=UTC)


@pytest.mark.parametrize(("source", "second", "expected"), [
    (
        "Regular soy consumption in men increases estrogen levels and lowers muscle gain.",
        "lowers muscle gain.",
        "Regular soy consumption in men lowers muscle gain.",
    ),
    (
        "Vitamin C may reduce cold duration and improve symptom severity.",
        "improve symptom severity.",
        "Vitamin C may improve symptom severity.",
    ),
    (
        "Smoking increases lung cancer risk and raises cardiovascular mortality.",
        "raises cardiovascular mortality.",
        "Smoking raises cardiovascular mortality.",
    ),
    (
        "Treatment X lowers blood pressure but increases dizziness.",
        "increases dizziness.",
        "Treatment X increases dizziness.",
    ),
    (
        "People taking X had lower fatigue and higher blood pressure.",
        "higher blood pressure.",
        "People taking X had higher blood pressure.",
    ),
    (
        "Smoking causes cancer. It also increases stroke risk.",
        "It also increases stroke risk.",
        "Smoking increases stroke risk.",
    ),
])
def test_source_grounded_shared_subject(source: str, second: str, expected: str) -> None:
    start = source.index(second)
    candidate = ExtractedClaimCandidate(
        raw_span=second, span_start=start, span_end=start + len(second),
        claim_type="causal", pico=PicoCandidate(outcome=second.split()[-1].rstrip(".")),
    )
    extracted = validate_claim_candidates(
        payload=ClaimExtractionPayload(claims=[candidate]), source_text=source,
        maximum_claims=20,
    )[0]
    assert extracted.raw_span == source[start:start + len(second)]
    assert extracted.normalized_claim == expected
    assert extracted.standalone_status == "reconstructed"
    assert extracted.coreference_uncertain is False
    assert extracted.resolved_from_span_start is not None
    assert extracted.resolved_from_span_end is not None
    assert source[
        extracted.resolved_from_span_start:extracted.resolved_from_span_end
    ] in expected
    pico = normalize_pico(extracted, source_text=source)
    assert pico.intervention_or_exposure is not None
    assert pico.intervention_or_exposure in expected


@pytest.mark.parametrize(("source", "second"), [
    ("It causes cancer.", "It causes cancer."),
    ("This reduces mortality.", "This reduces mortality."),
    ("Alcohol affects health. It causes cancer.", "It causes cancer."),
    ("Soy and whey increase strength and lower fatigue.", "lower fatigue."),
])
def test_uncertain_antecedent_never_becomes_standalone(source: str, second: str) -> None:
    start = source.rfind(second)
    candidate = ExtractedClaimCandidate(
        raw_span=second, span_start=start, span_end=len(source), claim_type="causal",
    )
    result = validate_claim_candidates(
        payload=ClaimExtractionPayload(claims=[candidate]), source_text=source,
        maximum_claims=20,
    )[0]
    assert result.standalone_status in {"uncertain", "incomplete"}
    assert result.normalized_claim is None
    assert not ready_for_evidence(
        "normalized", pico_json={}, quality_json={},
        standalone_status=result.standalone_status,
    )


def test_reconstruction_keeps_exact_raw_span_and_explicit_population() -> None:
    source = "Regular soy consumption in men increases estrogen levels and lowers muscle gain."
    second = "lowers muscle gain."
    start = source.index(second)
    candidate = ExtractedClaimCandidate(
        raw_span=second, span_start=start, span_end=len(source), claim_type="causal",
        pico=PicoCandidate(population="men", outcome="muscle gain"),
    )
    result = validate_claim_candidates(
        payload=ClaimExtractionPayload(claims=[candidate]), source_text=source,
        maximum_claims=20,
    )[0]
    pico = normalize_pico(result, source_text=source)
    assert pico.original_claim == second
    assert pico.population == "men"
    assert pico.intervention_or_exposure == "Regular soy consumption in men"
    assert pico.outcome == "muscle gain"
    assert source[result.resolved_from_span_start:result.resolved_from_span_end] == (
        "Regular soy consumption in men"
    )


def test_inflected_model_outcome_keeps_only_verbatim_source_endpoint() -> None:
    source = "Regular soy consumption in men increases estrogen levels."
    candidate = ExtractedClaimCandidate(
        raw_span=source, span_start=0, span_end=len(source), claim_type="causal",
        pico=PicoCandidate(
            intervention_or_exposure="Regular soy consumption",
            outcome="increased estrogen levels",
        ),
    )
    pico = normalize_pico(candidate, source_text=source)
    assert pico.outcome == "estrogen levels"
    invented = candidate.model_copy(update={
        "pico": PicoCandidate(outcome="increased testosterone levels"),
    })
    assert normalize_pico(invented, source_text=source).outcome is None


def _claim(outcome: str = "estrogen levels", population: str = "men") -> ClaimSnapshot:
    source = f"Regular soy consumption in {population} increases {outcome}."
    from app.pipeline.pico import NormalizedPico

    return ClaimSnapshot(
        claim_id=uuid4(), raw_text=source, claim_type="causal",
        pico=NormalizedPico(
            original_claim=source, population=population,
            intervention_or_exposure=f"Regular soy consumption in {population}",
            outcome=outcome, claim_type="causal",
        ),
    )


def _doc(pmid: str, title: str, label: str, abstract: str,
         mesh: tuple[str, ...] = ()) -> PubMedDocument:
    return PubMedDocument(
        document_id=f"pubmed:{pmid}", pmid=pmid, title=title, abstract=abstract,
        abstract_sections=(AbstractSection(label=label, text=abstract),),
        mesh_terms=mesh, canonical_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        retrieved_at=_NOW, content_sha256=pmid.zfill(64), query_ids=("Q1",),
    )


def _pack(claim: ClaimSnapshot, *docs: PubMedDocument):
    quality_docs = tuple(annotate_study_quality(claim, doc) for doc in docs)
    passages = tuple(passage for doc in quality_docs for passage in extract_passages(doc))
    return build_evidence_pack(
        claim, plan_pubmed_queries(claim), quality_docs,
        rank_passages(claim, quality_docs, passages),
    )


def test_endpoint_selection_prefers_measured_male_outcome_and_retains_indirect() -> None:
    claim = _claim()
    direct = _doc(
        "1001", "Soy intake and serum estrogen levels in men", "RESULTS",
        "Men consuming soy had no increase in measured serum estrogen concentrations.",
        ("Male", "Humans"),
    )
    mechanism = _doc(
        "1002", "Soy and estrogen-like effects", "BACKGROUND",
        "Soy has estrogen-like effects through estrogen receptor pathways.",
    )
    meningioma = _doc(
        "1003", "Soy intake and meningioma risk in men", "RESULTS",
        "Meningioma incidence was evaluated. Estrogen-associated mechanisms were discussed.",
    )
    bone = _doc(
        "1004", "Soy consumption and male bone health", "RESULTS",
        "The endpoint was osteoporosis and bone mineral density.",
    )
    women = _doc(
        "1005", "Soy intake and serum estrogen levels in women", "RESULTS",
        "Women consuming soy had measured serum estrogen concentrations.",
        ("Female", "Humans"),
    )
    pack = _pack(claim, mechanism, meningioma, bone, women, direct)
    by_doc = {doc.pmid: doc for doc in pack.documents}
    selected = {item.evidence_id: item for item in pack.passages}
    ordered = [
        selected[eid].passage.document_id.removeprefix("pubmed:")
        for eid in pack.selected_evidence_ids
    ]
    assert ordered[0] == "1001"
    assert by_doc["1001"].endpoint_directness.score > by_doc["1002"].endpoint_directness.score
    assert by_doc["1001"].endpoint_directness.score > by_doc["1003"].endpoint_directness.score
    assert by_doc["1001"].endpoint_directness.score > by_doc["1004"].endpoint_directness.score
    assert "female_only_vs_male_claim" in by_doc["1005"].applicability_warnings
    assert by_doc["1005"].endpoint_directness.score > by_doc["1003"].endpoint_directness.score
    assert len(pack.documents) == 5
    assert all(doc.document_id in {item.passage.document_id for item in pack.passages}
               for doc in pack.documents)


def test_quantitative_endpoint_does_not_fill_selection_with_indirect_papers() -> None:
    claim = _claim()
    direct = tuple(
        _doc(str(1100 + index), f"Soy and serum estrogen levels in men cohort {index}",
             "RESULTS", "Soy intake and measured estrogen concentrations in men were compared.")
        for index in range(3)
    )
    indirect = _doc(
        "1199", "Environmental estrogens and autoimmune pathways", "ABSTRACT",
        "Soy is mentioned among environmental estrogens, but the measured endpoint "
        "was autoimmune disease outcomes.",
    )
    pack = _pack(claim, *direct, indirect)
    assert EvidencePack.model_validate(pack.model_dump(mode="json")) == pack
    assert len(pack.selected_evidence_ids) == 3
    assert any(item.passage.document_id == indirect.document_id for item in pack.passages)
    assert not any(item.selected_for_judging for item in pack.passages
                   if item.passage.document_id == indirect.document_id)


def test_muscle_endpoint_not_generic_bone_or_performance() -> None:
    claim = _claim(outcome="muscle gain")
    direct = _doc("2001", "Soy protein and muscle gain in men", "RESULTS",
                  "Men consuming soy protein had measured changes in muscle mass.")
    indirect = _doc("2002", "Soy nutrition and exercise performance", "RESULTS",
                    "Exercise performance and general nutrition were studied.")
    pack = _pack(claim, indirect, direct)
    assert (pack.documents[0].endpoint_directness.score
            != pack.documents[1].endpoint_directness.score)
    by_id = {doc.document_id: doc for doc in pack.documents}
    assert by_id["pubmed:2001"].endpoint_directness.score > (
        by_id["pubmed:2002"].endpoint_directness.score
    )


def test_endpoint_query_keeps_broad_recall_separate_from_precision() -> None:
    plan = plan_pubmed_queries(_claim())
    assert any(query.family == "lexical" for query in plan.queries)
    assert any(query.family == "endpoint" and "serum" in query.query
               for query in plan.queries)
    assert any(query.family == "endpoint" and '"men"[Title/Abstract]' in query.query
               for query in plan.queries)


def test_negative_measured_result_is_still_endpoint_direct() -> None:
    claim = _claim()
    negative = _doc(
        "3001", "Soy and serum estrogen levels in men", "RESULTS",
        "Measured estrogen concentrations did not increase in men consuming soy.",
    )
    contextual = _doc(
        "3002", "Soy and estrogen-like pathways in men", "BACKGROUND",
        "Soy has estrogen-like receptor activity relevant to other outcomes.",
    )
    pack = _pack(claim, contextual, negative)
    by_id = {doc.pmid: doc for doc in pack.documents}
    assert by_id["3001"].endpoint_directness.score > by_id["3002"].endpoint_directness.score
    assert by_id["3001"].endpoint_directness.factors["endpoint_in_results"] == 1


def test_pack_hash_is_deterministic_and_endpoint_metadata_is_immutable() -> None:
    claim = _claim()
    doc = _doc("4001", "Soy and estrogen levels in men", "RESULTS",
               "Serum estrogen levels were measured in men consuming soy.")
    first = _pack(claim, doc)
    second = _pack(claim, doc)
    assert first.evidence_pack_version == "1.4"
    assert first.snapshot_hash == second.snapshot_hash
    restored = EvidencePack.model_validate(first.model_dump(mode="json"))
    digest = hashlib.sha256(canonical_pack_bytes(
        restored.claim_snapshot, restored.query_plan, restored.documents,
        restored.passages, restored.selected_evidence_ids,
        pack_version=restored.evidence_pack_version,
    )).hexdigest()
    assert digest == first.snapshot_hash
    changed = doc.model_copy(update={"title": "Soy and unrelated outcomes in men"})
    assert _pack(claim, changed).snapshot_hash != first.snapshot_hash


def test_background_factor_has_no_negative_zero_for_jsonb_round_trip() -> None:
    claim = _claim()
    background = _doc("4501", "Soy and contextual hormone biology", "BACKGROUND",
                      "Estrogen receptor pathways were discussed without a measured endpoint.")
    pack = _pack(claim, background)
    encoded = canonical_pack_bytes(
        pack.claim_snapshot, pack.query_plan, pack.documents,
        pack.passages, pack.selected_evidence_ids,
    )
    assert re.search(rb":-0\.0(?=[,}])", encoded) is None


def test_legacy_pack_13_hash_excludes_new_endpoint_defaults() -> None:
    claim = _claim()
    doc = _doc("5001", "Soy and estrogen levels in men", "RESULTS",
               "Serum estrogen levels were measured in men consuming soy.")
    current = _pack(claim, doc)
    legacy_hash = hashlib.sha256(canonical_pack_bytes(
        current.claim_snapshot, current.query_plan, current.documents,
        current.passages, current.selected_evidence_ids, pack_version="1.3",
    )).hexdigest()
    old_json = current.model_dump(mode="json")
    old_json["evidence_pack_version"] = "1.3"
    for document in old_json["documents"]:
        document.pop("endpoint_directness")
    for passage in old_json["passages"]:
        passage.pop("endpoint_directness")
    parsed = EvidencePack.model_validate(old_json)
    assert legacy_hash == hashlib.sha256(canonical_pack_bytes(
        parsed.claim_snapshot, parsed.query_plan, parsed.documents,
        parsed.passages, parsed.selected_evidence_ids, pack_version="1.3",
    )).hexdigest()
