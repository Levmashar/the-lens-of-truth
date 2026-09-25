"""Offline Phase 4B integrity, enrichment, quality, and audit contracts."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from app.adapters.crossref import CrossrefAdapter
from app.adapters.pubmed import PubMedAdapter
from app.pipeline.pico import NormalizedPico
from app.retrieval.evidence_pack import build_evidence_pack
from app.retrieval.integrity import merge_integrity, unavailable_crossref
from app.retrieval.models import ClaimSnapshot, CrossrefEnrichment, IntegrityCheck
from app.retrieval.normalize import parse_pubmed_xml, parse_pubmed_xml_details
from app.retrieval.passages import extract_passages
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import rank_passages
from app.retrieval.service import retrieve_pubmed
from app.retrieval.study_quality import annotate_study_quality, classify_study_design

_NOW = datetime(2026, 9, 25, tzinfo=UTC)
_XML = (Path(__file__).parent / "fixtures" / "pubmed_sample.xml").read_bytes()


def _claim(*, population: str | None = None) -> ClaimSnapshot:
    text = "Frequent sunscreen use causes invasive melanoma."
    return ClaimSnapshot(
        claim_id=UUID("11111111-1111-4111-8111-111111111111"),
        raw_text=text, claim_type="causal",
        pico=NormalizedPico(
            original_claim=text, claim_type="causal", population=population,
            intervention_or_exposure="Frequent sunscreen use", outcome="invasive melanoma",
        ),
    )


def _xml(
    *, publication_type: str | None = "Journal Article", relation: str | None = None,
    title: str = "Sunscreen use and melanoma risk", abstract: bool = True,
    doi: bool = True, pmid: str = "11111111",
) -> bytes:
    pub_type = (f"<PublicationTypeList><PublicationType>{publication_type}</PublicationType>"
                "</PublicationTypeList>") if publication_type else ""
    correction = (f'<CommentsCorrectionsList><CommentsCorrections RefType="{relation}">'
                  "<PMID>22222222</PMID></CommentsCorrections></CommentsCorrectionsList>") if (
                      relation
                  ) else ""
    abstract_xml = ("<Abstract><AbstractText>Sunscreen use and melanoma incidence were "
                    "examined.</AbstractText></Abstract>") if abstract else ""
    doi_xml = '<ArticleId IdType="doi">10.1234/example</ArticleId>' if doi else ""
    return (f"<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>{pmid}</PMID>"
            f"<Article><ArticleTitle>{title}</ArticleTitle>{abstract_xml}{pub_type}</Article>"
            f"{correction}</MedlineCitation><PubmedData><ArticleIdList>{doi_xml}"
            "</ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>").encode()


@pytest.mark.parametrize("pub_type,relation,expected", [
    ("Journal Article", None, "unknown"),
    ("Retracted Publication", None, "retracted"),
    ("Retraction Notice", "RetractionOf", "updated"),
    ("Journal Article", "RetractionIn", "retracted"),
    ("Published Erratum", "ErratumFor", "updated"),
    ("Journal Article", "ErratumIn", "corrected"),
    ("Corrected and Republished Article", None, "corrected"),
    ("Journal Article", "ExpressionOfConcernIn", "expression_of_concern"),
])
def test_structured_pubmed_integrity(
    pub_type: str, relation: str | None, expected: str,
) -> None:
    document = parse_pubmed_xml(_xml(publication_type=pub_type, relation=relation),
                                retrieved_at=_NOW)[0]
    assert document.integrity.status == expected
    assert document.integrity.checks[0].status == "checked"
    assert document.integrity.sources == ("pubmed",)
    if relation:
        assert document.integrity.references[0].identifier == "22222222"


def test_title_does_not_create_retraction_and_missing_metadata_is_unknown() -> None:
    titled = parse_pubmed_xml(_xml(title="Retraction: sunscreen use and melanoma risk"))[0]
    assert titled.integrity.status == "unknown"
    missing = parse_pubmed_xml(_xml(publication_type=None))[0]
    assert missing.integrity.status == "unknown"
    assert missing.integrity.checks[0].status == "unavailable"


def _crossref(handler: httpx.MockTransport, *, retries: int = 0, cache: object = None,
              ) -> CrossrefAdapter:
    return CrossrefAdapter(
        mailto="test@example.org", max_retries=retries, cache=cache,  # type: ignore[arg-type]
        client=httpx.AsyncClient(transport=handler, base_url="https://api.crossref.org/v1/"),
    )


def _work(**updates: object) -> dict[str, object]:
    return {"status": "ok", "message": {
        "DOI": "10.1234/example", "type": "journal-article", "publisher": "Test Publisher",
        "published": {"date-parts": [[2024, 9, 12]]},
        "deposited": {"date-parts": [[2026, 9, 1]]},
        **updates,
    }}


def test_crossref_success_and_cache_key_versioning() -> None:
    class MemoryCache:
        values: dict[str, str] = {}

        async def get(self, key: str) -> str | None:
            return self.values.get(key)

        async def set(self, key: str, value: str, ttl_seconds: int) -> None:
            assert ttl_seconds == 3600
            self.values[key] = value

    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        assert request.url.params["mailto"] == "test@example.org"
        return httpx.Response(200, json=_work())

    cache = MemoryCache()
    adapter = _crossref(httpx.MockTransport(handler), cache=cache)
    first = asyncio.run(adapter.enrich("10.1234/Example"))
    second = asyncio.run(adapter.enrich("10.1234/example"))
    assert first.check.status == second.check.status == "checked"
    assert first.publisher == "Test Publisher"
    assert first.work_type == "journal-article"
    assert first.published_date is not None
    assert first.deposited_date is not None
    assert len(requests) == 1
    assert len(cache.values) == 1
    assert next(iter(cache.values)).startswith("crossref:doi:")


@pytest.mark.parametrize("response,status,failure", [
    (httpx.Response(404), "not_found", None),
    (httpx.Response(429), "failed", "rate_limited"),
    (httpx.Response(200, content=b"garbage"), "failed", "malformed_response"),
    (httpx.Response(200, json={"status": "ok", "message": {"DOI": "10.9999/other"}}),
     "failed", "doi_mismatch"),
])
def test_crossref_non_success(
    response: httpx.Response, status: str, failure: str | None,
) -> None:
    adapter = _crossref(httpx.MockTransport(lambda _: response))
    enrichment = asyncio.run(adapter.enrich("10.1234/example"))
    assert enrichment.check.status == status
    assert enrichment.check.failure_type == failure


def test_crossref_timeout_retry_and_cache_failure_fail_open() -> None:
    class BrokenCache:
        async def get(self, _: str) -> str | None:
            raise ConnectionError("offline")

        async def set(self, _key: str, _value: str, _ttl: int) -> None:
            raise ConnectionError("offline")

    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json=_work())

    adapter = _crossref(httpx.MockTransport(handler), retries=1, cache=BrokenCache())
    assert asyncio.run(adapter.enrich("10.1234/example")).check.status == "checked"
    assert attempts == 2
    timeout = _crossref(httpx.MockTransport(
        lambda _: (_ for _ in ()).throw(httpx.ReadTimeout("slow"))
    ))
    assert asyncio.run(timeout.enrich("10.1234/example")).check.failure_type == "timeout"


def test_crossref_update_direction_and_merge_conflicts() -> None:
    pubmed = parse_pubmed_xml(_xml())[0]
    retraction = _work(**{"updated-by": [{
        "DOI": "10.1234/notice", "type": "retraction", "source": "publisher",
    }]})
    crossref = _crossref(httpx.MockTransport(lambda _: httpx.Response(200, json=retraction)))
    enriched = asyncio.run(crossref.enrich("10.1234/example"))
    assert enriched.references[0].signal == "retracted"
    assert enriched.references[0].assertion_source == "publisher"
    assert merge_integrity(pubmed, enriched).status == "retracted"
    notice = _work(**{"update-to": [{"DOI": "10.1234/original", "type": "retraction"}]})
    notice_adapter = _crossref(httpx.MockTransport(
        lambda _: httpx.Response(200, json=notice)
    ))
    notice_enriched = asyncio.run(notice_adapter.enrich("10.1234/example"))
    assert notice_enriched.references[0].signal is None
    assert merge_integrity(pubmed, notice_enriched).status == "valid"
    unknown_update = _work(**{"updated-by": [{
        "DOI": "10.1234/addendum", "type": "new_update_kind",
    }]})
    unknown_adapter = _crossref(httpx.MockTransport(
        lambda _: httpx.Response(200, json=unknown_update)
    ))
    assert merge_integrity(pubmed, asyncio.run(
        unknown_adapter.enrich("10.1234/example")
    )).status == "updated"
    pubmed_retracted = parse_pubmed_xml(_xml(publication_type="Retracted Publication"))[0]
    silent = _crossref(httpx.MockTransport(lambda _: httpx.Response(200, json=_work())))
    assert merge_integrity(pubmed_retracted, asyncio.run(
        silent.enrich("10.1234/example")
    )).status == "retracted"


def test_provider_failure_never_promotes_absence_to_valid() -> None:
    pubmed = parse_pubmed_xml(_xml())[0]
    failure = CrossrefEnrichment(
        doi=pubmed.doi, check=IntegrityCheck(
            source="crossref", status="failed", checked_at=_NOW,
            version="crossref-rest-1", failure_type="timeout",
        ),
    )
    merged = merge_integrity(pubmed, failure)
    assert merged.status == "unknown"
    assert "integrity_partially_checked" in merged.warnings
    assert merge_integrity(pubmed, unavailable_crossref(pubmed.doi)).status == "unknown"
    no_doi = parse_pubmed_xml(_xml(doi=False))[0]
    assert merge_integrity(no_doi, unavailable_crossref(None)).status == "valid"


def test_crossref_outage_keeps_pubmed_result_but_integrity_unknown() -> None:
    def pubmed_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["11111111"]}})
        return httpx.Response(200, content=_xml())

    pubmed = PubMedAdapter(
        tool="lens_test", email="test@example.org", max_retries=0,
        minimum_interval_seconds=0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(pubmed_handler),
                                 base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"),
    )
    crossref = _crossref(httpx.MockTransport(lambda _: httpx.Response(429)))
    result = asyncio.run(retrieve_pubmed(_claim(), pubmed, crossref=crossref))
    assert result.diagnostics.status == "ok"
    assert result.diagnostics.reason_counts["crossref_lookup_failed"] == 1
    assert result.pack.documents[0].integrity.status == "unknown"
    assert result.pack.documents[0].crossref.check.failure_type == "rate_limited"
    assert result.pack.selected_evidence_ids


def test_crossref_total_deadline_fails_open() -> None:
    def pubmed_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["11111111"]}})
        return httpx.Response(200, content=_xml())

    async def slow_crossref(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json=_work())

    pubmed = PubMedAdapter(
        tool="lens_test", email="test@example.org", max_retries=0,
        minimum_interval_seconds=0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(pubmed_handler),
                                 base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"),
    )
    crossref = _crossref(httpx.MockTransport(slow_crossref))
    result = asyncio.run(retrieve_pubmed(
        _claim(), pubmed, crossref=crossref, crossref_total_timeout_seconds=0.01,
    ))
    assert result.diagnostics.status == "ok"
    assert result.diagnostics.reason_counts["crossref_lookup_failed"] == 1
    assert result.pack.documents[0].crossref.check.failure_type == "deadline"
    assert result.pack.documents[0].integrity.status == "unknown"


@pytest.mark.parametrize("pub_type,mesh,title,expected", [
    ("Systematic Review", (), "A study", "systematic_review"),
    ("Meta-Analysis", (), "A study", "meta_analysis"),
    ("Randomized Controlled Trial", (), "A study", "randomized_controlled_trial"),
    ("Journal Article", ("Cohort Studies",), "A study", "cohort"),
    ("Journal Article", ("Case-Control Studies",), "A study", "case_control"),
    ("Review", (), "A study", "review"),
    ("Journal Article", ("Animals",), "A study", "animal_study"),
    ("Editorial", (), "A study", "editorial_or_commentary"),
    ("Journal Article", (), "A study", "unknown"),
])
def test_study_design_priority(
    pub_type: str, mesh: tuple[str, ...], title: str, expected: str,
) -> None:
    document = parse_pubmed_xml(_xml(publication_type=pub_type, title=title))[0]
    document = document.model_copy(update={"mesh_terms": mesh})
    assert classify_study_design(document)[0] == expected


def test_quality_prior_and_applicability_are_separate_from_topical_score() -> None:
    claim = _claim(population="adults")
    animal = parse_pubmed_xml(_xml())[0].model_copy(update={"mesh_terms": ("Animals",)})
    animal = annotate_study_quality(claim, animal)
    assert animal.study_design == "animal_study"
    assert animal.applicability_warnings == ("animal_to_human",)
    assert animal.quality_prior < 0.4
    ranked = rank_passages(claim, (animal,), extract_passages(animal))
    assert ranked[0].retrieval_score > 0
    assert "quality_prior" not in ranked[0].factors


def test_retracted_remains_auditable_but_not_selected_and_hash_changes() -> None:
    claim = _claim()
    direct = parse_pubmed_xml(_xml())[0]
    retracted = parse_pubmed_xml(_xml(pmid="22222222", publication_type="Retracted Publication"))[0]
    retracted = retracted.model_copy(update={"integrity": merge_integrity(
        retracted, unavailable_crossref(retracted.doi),
    )})
    direct = direct.model_copy(update={"integrity": merge_integrity(
        direct, unavailable_crossref(direct.doi),
    )})
    documents = (direct, retracted)
    passages = tuple(p for document in documents for p in extract_passages(document))
    ranked = rank_passages(claim, documents, passages)
    plan = plan_pubmed_queries(claim)
    pack = build_evidence_pack(claim, plan, documents, ranked)
    selected = {item.passage.document_id for item in pack.passages if item.selected_for_judging}
    assert selected == {direct.document_id}
    assert {item.passage.document_id for item in pack.passages} == {
        direct.document_id, retracted.document_id,
    }
    assert all(item.selection_reason == "retracted_excluded" for item in pack.passages
               if item.passage.document_id == retracted.document_id)
    assert pack.evidence_pack_version == "1.3"
    assert pack.snapshot_hash == build_evidence_pack(claim, plan, documents, ranked).snapshot_hash
    changed = retracted.model_copy(update={"integrity": direct.integrity})
    revised = build_evidence_pack(claim, plan, (direct, changed), ranked)
    assert revised.snapshot_hash != pack.snapshot_hash
    assert pack.documents[1].integrity.status == "retracted"
    assert revised.documents[1].integrity.status == "unknown"


def test_irrelevant_review_does_not_beat_direct_paper() -> None:
    claim = _claim()
    direct = annotate_study_quality(claim, parse_pubmed_xml(_xml())[0])
    review = parse_pubmed_xml(_xml(
        pmid="33333333", publication_type="Systematic Review",
        title="Epidemiology of melanoma", abstract=False,
    ))[0]
    review = annotate_study_quality(claim, review)
    assert review.quality_prior > direct.quality_prior
    docs = (direct, review)
    ranked = rank_passages(claim, docs, tuple(p for d in docs for p in extract_passages(d)))
    pack = build_evidence_pack(claim, plan_pubmed_queries(claim), docs, ranked)
    first_selected = next(p for p in pack.passages
                          if p.evidence_id == pack.selected_evidence_ids[0])
    assert first_selected.passage.document_id == direct.document_id
    assert len({p.passage.document_id for p in pack.passages if p.selected_for_judging}) == 2


def test_optional_metadata_and_efetch_gaps_are_distinguished() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": [
                "11111111", "22222222", "33333333",
            ]}})
        incomplete = b"<PubmedArticle><MedlineCitation><PMID>22222222</PMID>" \
                     b"<Article></Article></MedlineCitation></PubmedArticle>"
        xml = _xml(doi=False, abstract=False)
        return httpx.Response(200, content=xml.replace(b"</PubmedArticleSet>",
                                                       incomplete + b"</PubmedArticleSet>"))

    adapter = PubMedAdapter(
        tool="lens_test", email="test@example.org", max_retries=0,
        minimum_interval_seconds=0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                 base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"),
    )
    result = asyncio.run(retrieve_pubmed(_claim(), adapter))
    assert result.diagnostics.status == "partial_metadata"
    assert result.diagnostics.missing_pmids == ("22222222", "33333333")
    reasons = result.diagnostics.reason_counts
    assert reasons["optional_doi_absent"] == 1
    assert reasons["optional_abstract_absent"] == 1
    assert reasons["crossref_not_applicable"] == 1
    assert reasons["incomplete_publication_date"] == 1
    assert reasons["incomplete_efetch_record"] == 1
    assert reasons["missing_efetch_record"] == 1
    assert result.pack.documents[0].integrity.status == "valid"
    assert parse_pubmed_xml_details(_xml(doi=False)).incomplete_pmids == ()


def test_optional_doi_absence_alone_is_not_partial_metadata() -> None:
    xml = _xml(doi=False)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["11111111"]}})
        return httpx.Response(200, content=xml)

    adapter = PubMedAdapter(
        tool="lens_test", email="test@example.org", max_retries=0,
        minimum_interval_seconds=0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                 base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"),
    )
    result = asyncio.run(retrieve_pubmed(_claim(), adapter))
    assert result.diagnostics.status == "ok"
    assert result.diagnostics.reason_counts["optional_doi_absent"] == 1


def test_book_record_is_reported_as_unsupported_not_missing_fetch() -> None:
    book = (b"<PubmedArticleSet><PubmedBookArticle><BookDocument>"
            b"<PMID>28722978</PMID><ArticleTitle>Skin Cancer</ArticleTitle>"
            b"</BookDocument></PubmedBookArticle></PubmedArticleSet>")
    parsed = parse_pubmed_xml_details(book)
    assert parsed.documents == ()
    assert parsed.seen_pmids == ("28722978",)
    assert parsed.unsupported_pmids == ("28722978",)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["28722978"]}})
        return httpx.Response(200, content=book)

    adapter = PubMedAdapter(
        tool="lens_test", email="test@example.org", max_retries=0,
        minimum_interval_seconds=0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                 base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"),
    )
    result = asyncio.run(retrieve_pubmed(_claim(), adapter))
    assert result.diagnostics.status == "partial_metadata"
    assert result.diagnostics.reason_counts == {"unsupported_efetch_record_type": 1}
    assert result.diagnostics.missing_pmids == ("28722978",)


def test_fixture_contract_still_loads() -> None:
    assert len(parse_pubmed_xml(_XML)) == 2
