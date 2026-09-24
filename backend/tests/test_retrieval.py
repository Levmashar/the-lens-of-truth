"""Offline Phase 4A contracts, using official-format NCBI fixtures only."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from app.adapters.pubmed import PubMedAdapter, RedisQueryCache
from app.medical.entities import MedicalEntity
from app.pipeline.pico import NormalizedPico
from app.retrieval.errors import RetrievalError
from app.retrieval.evidence_pack import build_evidence_pack, deduplicate_documents
from app.retrieval.models import ClaimSnapshot
from app.retrieval.normalize import parse_pubmed_xml
from app.retrieval.passages import extract_passages
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import rank_passages
from app.retrieval.service import retrieve_pubmed

XML = (Path(__file__).parent / "fixtures" / "pubmed_sample.xml").read_bytes()
CLAIM_ID = UUID("11111111-1111-4111-8111-111111111111")


def claim(text: str, kind: str = "causal", *, linked: bool = True) -> ClaimSnapshot:
    entities = (
        MedicalEntity(surface_text="sunscreen", entity_type="intervention_or_exposure",
                      mesh_id="D013473", preferred_name="Sunscreening Agents",
                      match_type="synonym", confidence=0.95,
                      terminology_source="mesh", terminology_version="2026"),
        MedicalEntity(surface_text="melanoma", entity_type="outcome",
                      mesh_id="D008545", preferred_name="Melanoma",
                      match_type="exact", confidence=1.0,
                      terminology_source="mesh", terminology_version="2026"),
    ) if linked else ()
    return ClaimSnapshot(
        claim_id=CLAIM_ID, raw_text=text, claim_type=kind,
        pico=NormalizedPico(original_claim=text, claim_type=kind,
                            intervention_or_exposure="Frequent sunscreen use",
                            outcome="invasive melanoma"),
        entities=entities,
    )


def test_query_planning_mesh_lexical_causal_and_numeric() -> None:
    snapshot = claim("Frequent sunscreen use causes a 292% increase in invasive melanoma risk.")
    plan = plan_pubmed_queries(snapshot)
    assert [query.family for query in plan.queries] == [
        "mesh", "lexical", "relation", "distinctive",
    ]
    assert '"Sunscreening Agents"[MeSH Terms]' in plan.queries[0].query
    assert '"Melanoma"[MeSH Terms]' in plan.queries[0].query
    assert "sunscreen" in plan.queries[1].query
    assert "292%" in plan.queries[3].query
    assert all(query.relation_semantics == "causal" for query in plan.queries)
    assert all("population" not in query.source_fields for query in plan.queries)
    assert all("comparator" not in query.source_fields for query in plan.queries)


def test_distinctive_source_count_is_preserved() -> None:
    snapshot = claim(
        "A cohort of 470,000 participants found sunscreen use causes invasive melanoma."
    )
    plan = plan_pubmed_queries(snapshot)
    numeric = next(query for query in plan.queries if query.family == "distinctive")
    assert "470,000" in numeric.query


@pytest.mark.parametrize("kind,expected", [
    ("association", "association"), ("prevention", "prevention"),
])
def test_relation_semantics_are_not_collapsed(kind: str, expected: str) -> None:
    snapshot = claim("Frequent sunscreen use is associated with higher melanoma risk.", kind)
    plan = plan_pubmed_queries(snapshot)
    relation = next(query for query in plan.queries if query.family == "relation")
    assert relation.relation_semantics == expected
    assert expected in relation.query


def test_unresolved_entity_has_lexical_fallback() -> None:
    plan = plan_pubmed_queries(claim("Frequent sunscreen use causes invasive melanoma.",
                                     linked=False))
    assert "mesh" not in [query.family for query in plan.queries]
    assert "lexical" in [query.family for query in plan.queries]


def test_pubmed_parsing_preserves_metadata_and_missing_fields() -> None:
    documents = parse_pubmed_xml(XML, retrieved_at=datetime(2026, 9, 24, tzinfo=UTC))
    assert len(documents) == 2
    first, second = documents
    assert first.pmid == "12345678"
    assert first.doi == "10.1/example"
    assert first.publication_date is not None
    assert len(first.abstract_sections) == 2
    assert first.abstract_sections[1].label == "RESULTS"
    assert first.publication_types == ("Journal Article", "Observational Study")
    assert first.mesh_terms == ("Sunscreening Agents", "Melanoma")
    assert first.authors == ("Alex Example",)
    assert second.doi is None
    assert second.abstract is None
    assert [item.section for item in extract_passages(first)] == ["TITLE", "BACKGROUND", "RESULTS"]
    assert [item.section for item in extract_passages(second)] == ["TITLE"]


@pytest.mark.parametrize("bad", [
    b"<oops>", b"<x/>",
    b'<!DOCTYPE PubmedArticleSet [<!ENTITY bomb "boom">]><PubmedArticleSet/>',
])
def test_malformed_pubmed_xml_is_typed_failure(bad: bytes) -> None:
    with pytest.raises(RetrievalError) as error:
        parse_pubmed_xml(bad)
    assert error.value.kind == "malformed_response"


def test_official_pubmed_doctype_is_accepted_without_entity_expansion() -> None:
    declared = (
        b'<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle//EN" '
        b'"https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed.dtd">\n' + XML
    )
    assert len(parse_pubmed_xml(declared)) == 2


def test_dedup_keeps_all_query_provenance() -> None:
    document = parse_pubmed_xml(XML)[0]
    result = deduplicate_documents((
        document.model_copy(update={"query_ids": ("Q1",)}),
        document.model_copy(update={"query_ids": ("Q2", "Q3")}),
    ))
    assert len(result) == 1
    assert result[0].query_ids == ("Q1", "Q2", "Q3")


def test_ranking_and_pack_are_deterministic_and_content_sensitive() -> None:
    snapshot = claim("Frequent sunscreen use causes invasive melanoma.")
    documents = parse_pubmed_xml(XML)
    documents = tuple(item.model_copy(update={"query_ids": ("Q1", "Q2")})
                      for item in documents)
    passages = tuple(p for document in documents for p in extract_passages(document))
    ranked = rank_passages(snapshot, documents, passages)
    assert ranked == rank_passages(snapshot, documents, passages)
    assert ranked[0].retrieval_score >= ranked[-1].retrieval_score
    assert ranked[0].factors["exposure_match"] > 0
    assert ranked[0].factors["outcome_match"] > 0
    assert [item.evidence_id for item in ranked] == [f"E{i}" for i in range(1, len(ranked) + 1)]
    plan = plan_pubmed_queries(snapshot)
    pack = build_evidence_pack(snapshot, plan, documents, ranked)
    later = build_evidence_pack(snapshot, plan, documents, ranked,
                                retrieved_at=datetime(2030, 1, 1, tzinfo=UTC))
    assert pack.snapshot_hash == later.snapshot_hash
    assert "verdict" not in pack.model_dump()
    assert pack.passages[0].passage.document_id.startswith("pubmed:")
    changed = ranked[0].passage.model_copy(update={"text": "Changed source text"})
    changed_rank = ranked[0].model_copy(update={"passage": changed})
    changed_pack = build_evidence_pack(snapshot, plan, documents, (changed_rank, *ranked[1:]))
    assert changed_pack.snapshot_hash != pack.snapshot_hash


def _adapter(handler: httpx.MockTransport, *, max_retries: int = 0) -> PubMedAdapter:
    return PubMedAdapter(
        tool="lens_test", email="test@example.org", max_retries=max_retries,
        minimum_interval_seconds=0, client=httpx.AsyncClient(
            transport=handler, base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
        ),
    )


def test_adapter_zero_results_and_normal_flow() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            assert request.url.params["tool"] == "lens_test"
            return httpx.Response(200, json={"esearchresult": {"idlist": ["12345678"]}})
        return httpx.Response(200, content=XML)

    adapter = _adapter(httpx.MockTransport(handler))
    result = asyncio.run(retrieve_pubmed(
        claim("Frequent sunscreen use causes invasive melanoma."), adapter,
    ))
    assert result.diagnostics.status == "ok"
    assert len(result.pack.documents) == 1
    assert len(result.pack.documents[0].query_ids) >= 2
    assert result.pack.passages[0].evidence_id == "E1"

    empty_adapter = _adapter(httpx.MockTransport(lambda _: httpx.Response(
        200, json={"esearchresult": {"idlist": []}},
    )))
    empty = asyncio.run(retrieve_pubmed(
        claim("Frequent sunscreen use causes invasive melanoma."), empty_adapter,
    ))
    assert empty.diagnostics.status == "no_results"
    assert empty.pack.documents == ()
    assert empty.pack.passages == ()


@pytest.mark.parametrize("response,kind", [
    (httpx.Response(429), "rate_limited"),
    (httpx.Response(503), "upstream_http"),
    (httpx.Response(200, content=b"not-json"), "malformed_response"),
])
def test_adapter_classifies_errors(response: httpx.Response, kind: str) -> None:
    adapter = _adapter(httpx.MockTransport(lambda _: response))
    with pytest.raises(RetrievalError) as error:
        asyncio.run(adapter.search("sunscreen"))
    assert error.value.kind == kind


def test_adapter_timeout_and_transport_are_typed() -> None:
    for exception, expected in ((httpx.ReadTimeout("slow"), "timeout"),
                                (httpx.ConnectError("offline"), "transport")):
        def fail(_: httpx.Request, error: Exception = exception) -> httpx.Response:
            raise error
        adapter = _adapter(httpx.MockTransport(fail))
        with pytest.raises(RetrievalError) as error:
            asyncio.run(adapter.search("sunscreen"))
        assert error.value.kind == expected


def test_adapter_retries_transient_failure_once() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"esearchresult": {"idlist": ["12345678"]}})

    adapter = _adapter(httpx.MockTransport(handler), max_retries=1)
    ids, cached = asyncio.run(adapter.search("sunscreen"))
    assert attempts == 2
    assert ids == ("12345678",)
    assert not cached


def test_adapter_cache_hit_avoids_network_and_key_is_versioned() -> None:
    keys: list[str] = []

    class MemoryCache:
        async def get(self, key: str) -> str | None:
            keys.append(key)
            return '["12345678"]'

        async def set(self, key: str, value: str, ttl_seconds: int) -> None:
            raise AssertionError("Cache hit should not write")

    def fail(_: httpx.Request) -> httpx.Response:
        raise AssertionError("Cache hit should not access PubMed")

    adapter = PubMedAdapter(
        tool="lens_test", email="test@example.org", cache=MemoryCache(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(fail),
                                 base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"),
    )
    ids, hit = asyncio.run(adapter.search(" sunscreen   AND  melanoma "))
    assert ids == ("12345678",)
    assert hit
    assert keys[0].startswith("pubmed:esearch:")


def test_esearch_rate_limit_body_is_classified() -> None:
    adapter = _adapter(httpx.MockTransport(lambda _: httpx.Response(
        200, json={"error": "API rate limit exceeded"},
    )))
    with pytest.raises(RetrievalError) as error:
        asyncio.run(adapter.search("sunscreen"))
    assert error.value.kind == "rate_limited"


def test_redis_cache_outage_fails_open() -> None:
    class BrokenRedis:
        async def get(self, _: str) -> str:
            raise ConnectionError("cache offline")

        async def set(self, _key: str, _value: str, *, ex: int) -> None:
            raise ConnectionError("cache offline")

    cache = RedisQueryCache("redis://localhost:6379/0")
    cache._client = BrokenRedis()  # type: ignore[assignment]
    assert asyncio.run(cache.get("key")) is None
    asyncio.run(cache.set("key", "value", 60))


def test_partial_metadata_does_not_fabricate_missing_document() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": [
                "12345678", "99999999",
            ]}})
        return httpx.Response(200, content=XML)

    result = asyncio.run(retrieve_pubmed(
        claim("Frequent sunscreen use causes invasive melanoma."),
        _adapter(httpx.MockTransport(handler)),
    ))
    assert result.diagnostics.status == "partial_metadata"
    assert result.diagnostics.missing_pmids == ("99999999",)
    assert len(result.pack.documents) == 1


def test_distinct_pmids_with_same_title_remain_distinct() -> None:
    first, second = parse_pubmed_xml(XML)
    same_title = second.model_copy(update={"title": first.title})
    assert len(deduplicate_documents((first, same_title))) == 2


def test_association_regression_through_pack_metadata() -> None:
    snapshot = claim("Frequent sunscreen use is associated with higher melanoma risk.",
                     "association")
    document = parse_pubmed_xml(XML)[0].model_copy(update={"query_ids": ("Q1",)})
    plan = plan_pubmed_queries(snapshot)
    ranked = rank_passages(snapshot, (document,), extract_passages(document))
    pack = build_evidence_pack(snapshot, plan, (document,), ranked)
    assert pack.claim_snapshot.claim_type == "association"
    assert pack.query_plan.claim_type == "association"
    assert all(query.relation_semantics == "association" for query in plan.queries)
