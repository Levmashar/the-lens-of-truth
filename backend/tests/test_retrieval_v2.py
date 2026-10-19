"""Adaptive search, origin verification, conservative scope and historical hashes."""

import asyncio
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.adapters.discovery import DiscoveryLead, ScholarlyDiscovery
from app.adapters.official_web import OfficialWebDiscovery, safe_url
from app.pipeline.pico import NormalizedPico
from app.retrieval.adaptive import classify, plan_adaptive_queries
from app.retrieval.errors import RetrievalError
from app.retrieval.evidence_pack import build_evidence_pack, canonical_pack_bytes
from app.retrieval.models import (
    AbstractSection,
    ClaimSnapshot,
    DocumentIntegrity,
    IntegrityCheck,
    PubMedDocument,
    PubMedFetchResult,
)
from app.retrieval.passages import extract_passages
from app.retrieval.ranking import rank_passages
from app.retrieval.v2 import identity_matches, retrieve_adaptive


def claim(exposure="Using a tablet while lying on your side", outcome="myopia progression"):
    text = f"{exposure} increases {outcome}."
    return ClaimSnapshot(
        claim_id=uuid4(),
        raw_text=text,
        claim_type="causal",
        pico=NormalizedPico(
            original_claim=text,
            intervention_or_exposure=exposure,
            outcome=outcome,
            claim_type="causal",
        ),
    )


def document(title="Tablet use and myopia progression", abstract=None, pmid="123"):
    text = abstract or "Tablet use was associated with myopia progression in a cohort of adults."
    return PubMedDocument(
        document_id="pubmed:" + pmid,
        pmid=pmid,
        title=title,
        abstract=text,
        abstract_sections=(AbstractSection(label="RESULTS", text=text),),
        canonical_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        retrieved_at=datetime.now(UTC),
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
        publication_types=("Observational Study",),
        integrity=DocumentIntegrity(
            status="valid",
            checks=(IntegrityCheck(source="pubmed", status="checked", version="test"),),
        ),
    )


def test_search_preserves_qualifiers_and_broadens_only_search():
    c = claim()
    before = c.model_dump(mode="json")
    plan = plan_adaptive_queries(c)
    assert plan.version == "2.0" and len(plan.queries) <= 5
    assert '"your"' not in plan.queries[0].query
    assert '"while"' not in plan.queries[0].query
    assert '"side"' in plan.queries[0].query
    assert '"lateral"' in plan.queries[0].query
    broad = next(q for q in plan.queries if q.family == "broad_context")
    assert '"side"' not in broad.query and '"tablet"' in broad.query
    assert all("myopia" in q.query for q in plan.queries)
    assert before == c.model_dump(mode="json")


@pytest.mark.parametrize(
    "field,value,missing",
    [
        ("population", "children", "population:children"),
        ("comparator", "placebo", "comparator:placebo"),
        ("timeframe", "five years", "timeframe:five"),
    ],
)
def test_classification_never_infers_missing_scope(field, value, missing):
    c = claim(exposure="Tablet use")
    c = c.model_copy(update={"pico": c.pico.model_copy(update={field: value})})
    result = classify(c, document())
    assert result.classification == "related_indirect"
    assert missing in result.missing_qualifiers


def test_progression_is_not_interchangeable_with_prevalence_or_topic():
    c = claim(exposure="Tablet use")
    d = document(
        title="Tablet use and myopia prevalence",
        abstract="Tablet use was associated with myopia prevalence in adults.",
    )
    assert classify(c, d).classification == "related_indirect"
    assert "outcome:progression" in classify(c, d).missing_qualifiers
    assert classify(c, document(title="Device screening for myopia")).classification == "irrelevant"


def test_cross_provider_identity_requires_metadata_and_preserves_versions():
    d = document()
    lead = DiscoveryLead("openalex", "W1", d.pmid, None, d.title, "article")
    assert identity_matches(lead, d)
    assert not identity_matches(lead, d.model_copy(update={"pmid": "456"}))
    assert not identity_matches(lead, d.model_copy(update={"title": "Another review of myopia"}))
    assert not identity_matches(
        DiscoveryLead("openalex", "W1", d.pmid, "10.1/other", d.title, "article"),
        d.model_copy(update={"doi": "10.1/actual"}),
    )


class MemoryCache:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ttl_seconds):
        self.values[key] = value


def test_discovery_is_cached_and_failure_is_not_a_no_results_success():
    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            if request.url.host == "api.openalex.org":
                return httpx.Response(429)
            return httpx.Response(
                200,
                json={
                    "resultList": {
                        "result": [{"source": "MED", "id": "123", "title": "An indexed paper"}]
                    }
                },
            )

        adapter = ScholarlyDiscovery(
            cache=MemoryCache(), client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
        assert len(await adapter.search("europe_pmc", "tablet AND myopia")) == 1
        assert len(await adapter.search("europe_pmc", "tablet AND myopia")) == 1
        assert adapter.executions[-1]["cache_hit"] is True
        assert await adapter.search("openalex", "tablet myopia") == ()
        assert adapter.executions[-1]["status"] == "failed"
        assert len(calls) == 2

    asyncio.run(run())


class PublicAdapter:
    last_search_diagnostics = {}

    def __init__(self, doc=None, fail=False):
        self.doc, self.fail = doc, fail

    async def search(self, query):
        if self.fail:
            raise RetrievalError("timeout")
        return (), False

    async def fetch_cached(self, ids):
        return PubMedFetchResult(documents=(self.doc,) if self.doc and ids else ())


def test_discovered_duplicate_hydrates_once_and_is_indirect_not_a_vote():
    async def run():
        d = document()

        def handler(request):
            if request.url.host == "api.openalex.org":
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "id": "W1",
                                "title": d.title,
                                "ids": {"pmid": "https://pubmed.ncbi.nlm.nih.gov/123/"},
                                "type": "article",
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={"resultList": {"result": [{"source": "MED", "id": "123", "title": d.title}]}},
            )

        discovery = ScholarlyDiscovery(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
        result = await retrieve_adaptive(claim(), PublicAdapter(d), discovery=discovery)
        assert len(result.pack.documents) == 1
        frozen = result.pack.documents[0]
        assert frozen.retrieval_context.classification == "related_indirect"
        assert frozen.evidence_role_hint == "contextual"
        assert set(frozen.retrieval_context.discovery_providers) == {"openalex", "europe_pmc"}
        assert len(result.pack.selected_evidence_ids) == 1
        assert result.diagnostics.adaptive["model_calls"] == 0

    asyncio.run(run())


def test_all_provider_failures_are_operational_failure():
    async def run():
        discovery = ScholarlyDiscovery(
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(503))
            )
        )
        result = await retrieve_adaptive(claim(), PublicAdapter(fail=True), discovery=discovery)
        assert result.diagnostics.status == "failed"
        assert not result.pack.selected_evidence_ids

    asyncio.run(run())


def test_v2_scope_hash_is_binding_without_changing_historical_hash():
    c, d = claim(), document()
    plan = plan_adaptive_queries(c)
    ranked = rank_passages(c, (d,), extract_passages(d))
    pack = build_evidence_pack(c, plan, (d,), ranked, pack_version="2.0")
    context = pack.documents[0].retrieval_context.model_copy(update={"missing_qualifiers": ()})
    changed = pack.documents[0].model_copy(update={"retrieval_context": context})

    def digest(version, docs):
        return hashlib.sha256(
            canonical_pack_bytes(
                c, plan, docs, pack.passages, pack.selected_evidence_ids, pack_version=version
            )
        ).hexdigest()

    assert digest("2.0", (changed,)) != pack.snapshot_hash
    old = pack.documents[0].model_copy(update={"retrieval_context": None})
    assert digest("1.5", (changed,)) == digest("1.5", (old,))


@pytest.mark.parametrize(
    "url",
    [
        "http://www.nhs.uk/conditions/example/",
        "https://www.nhs.uk.evil.test/condition/",
        "https://user@www.nhs.uk/condition/",
        "https://www.nhs.uk:8443/condition/",
        "https://127.0.0.1/",
        "https://www.nhs.uk/search?q=anything",
    ],
)
def test_controlled_web_rejects_noncanonical_or_unapproved_urls(url):
    assert safe_url(url) is None


def test_official_page_content_not_search_snippets_is_frozen_as_background():
    async def run():
        url = "https://www.nhs.uk/conditions/eye-condition/"
        text = "Tablet use and myopia are discussed in this clinical information. " * 4

        def handler(request):
            if request.url.host == "wsearch.nlm.nih.gov":
                return httpx.Response(
                    200,
                    text='<nlm><document url="https://blog.test/a">'
                    "<content>UNTRUSTED SEARCH SNIPPET</content></document></nlm>",
                )
            if request.url.path == "/search/results":
                return httpx.Response(
                    200, text=f'<main><a href="{url}">An official result</a></main>'
                )
            return httpx.Response(
                200,
                text=f'<link rel="canonical" href="{url}">'
                f"<main><h1>Clinical eye guidance</h1><p>{text}</p></main>",
            )

        web = OfficialWebDiscovery(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        docs = await web.retrieve(claim(), "tablet myopia")
        assert len(docs) == 1
        assert docs[0].abstract == text.strip()
        assert docs[0].authoritative.currency == "unknown"
        assert docs[0].integrity.status == "unknown"
        assert docs[0].evidence_role_hint == "contextual"
        assert "UNTRUSTED" not in docs[0].model_dump_json()

    asyncio.run(run())


def test_indirect_scope_cannot_be_overridden_by_strong_validator_axes():
    from test_validated_evidence_position import position_contract, saved

    from app.validation.joint24 import qualification_input24
    from app.validation.position import derive_position

    old, pack, response = saved("sunscreen")
    judge = position_contract(old, pack)
    data = qualification_input24(judge, pack, response, "standard")
    context = {
        **data.relationship_context,
        "retrieval_scope_ceiling": {a.statement_id: True for a in data.assessments},
    }
    position = derive_position(data.model_copy(update={"relationship_context": context}))
    assert position.validated_evidence_position == "not_enough_evidence"
    assert not position.output.decisive_statement_ids


def test_document_v2_freezes_discovery_and_keeps_assertion_owned_catalog():
    from app.document.retrieval import GroupEvidenceSnapshot, retrieve_document_group
    from tests.test_document_retrieval import _plan, _PubMed

    class Adapter(_PubMed):
        async def fetch_cached(self, ids):
            return await self.fetch(ids)

    async def run():
        plan = _plan()
        discovery = ScholarlyDiscovery(
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda r: httpx.Response(
                        200, json={"results": [], "resultList": {"result": []}}
                    )
                )
            )
        )
        evidence = await retrieve_document_group(
            uuid4(), plan, plan.groups[0], Adapter(), discovery=discovery
        )
        assert evidence.version == "document-evidence-2.0"
        assert evidence.pack.evidence_pack_version == "2.0"
        assert evidence.pack.query_plan.version == "2.0"
        assert evidence.discovery_audit["canonical_identity_required"]
        assert set(evidence.per_assertion_evidence_ids) == {"A1", "A2"}
        assert GroupEvidenceSnapshot.model_validate_json(evidence.model_dump_json()) == evidence
        assert (
            hashlib.sha256(
                canonical_pack_bytes(
                    evidence.pack.claim_snapshot,
                    evidence.pack.query_plan,
                    evidence.pack.documents,
                    evidence.pack.passages,
                    evidence.pack.selected_evidence_ids,
                    pack_version="2.0",
                )
            ).hexdigest()
            == evidence.pack.snapshot_hash
        )

    asyncio.run(run())


def test_reviewed_authoritative_summary_keeps_existing_direct_role():
    from app.adapters.authoritative import ApprovedSource, freeze_html

    now = datetime.now(UTC)
    source = ApprovedSource(
        source_id="synthetic-summary",
        organization="NCI",
        canonical_url="https://www.cancer.gov/about-cancer/causes-prevention/example",
        document_title="Synthetic reviewed evidence summary",
        document_purpose="systematic_evidence_summary",
        topic_terms=("tablet",),
        root_attribute="tag",
        root_value="main",
        last_verified_at=now,
        retrieval_method="html_blocks",
        independence_group="synthetic",
        attribution="Synthetic",
    )
    html = f'<time datetime="{now.date()}"></time><main><p>Tablet use was associated with '
    html += "myopia progression in this synthetic evidence summary for software testing.</p></main>"
    d = freeze_html(source, html, now=now)
    assert d.authoritative.currency == "current"
    assert classify(claim("Tablet use"), d).classification == "direct"
    changed = d.model_copy(
        update={"metadata_provenance": {"purpose": "background_only_automated_origin_verification"}}
    )
    assert classify(claim("Tablet use"), changed).classification == "background_guidance"
    from app.retrieval.adaptive import constrain_selection

    c = claim("Tablet use")
    old = build_evidence_pack(
        c,
        plan_adaptive_queries(c),
        (d,),
        rank_passages(c, (d,), extract_passages(d)),
        pack_version="1.5",
    )
    assert old.documents[0].evidence_role_hint == "direct"
    passages = tuple(
        p.model_copy(update={"selection_reason": "direct_title_evidence_available"})
        if p.passage.section == "TITLE"
        else p
        for p in old.passages
    )
    docs, _, ids = constrain_selection(
        c, old.documents, passages, old.selected_evidence_ids, limit=8
    )
    assert docs[0].evidence_role_hint == "direct"
    assert docs[0].retrieval_context.classification == "direct"
    assert ids == old.selected_evidence_ids


def test_fully_matched_everyday_exposure_can_enter_without_literal_sentence_match():
    c = claim()
    text = "Tablet use while lying on the side was associated with myopia progression in adults."
    d = document(title="Tablet posture and myopia progression", abstract=text)
    ranked = rank_passages(c, (d,), extract_passages(d))
    pack = build_evidence_pack(c, plan_adaptive_queries(c), (d,), ranked, pack_version="2.0")
    assert pack.selected_evidence_ids
    assert pack.documents[0].retrieval_context.classification == "direct"
    assert pack.documents[0].evidence_role_hint == "direct"


def test_searches_retain_medical_concept_atoms_and_endpoint_stage():
    from app.medical.entities import MedicalEntity

    c = claim("Regular vitamin C supplementation", "developing respiratory illness")
    c = c.model_copy(
        update={
            "entities": (
                MedicalEntity(
                    surface_text="vitamin C",
                    entity_type="intervention_or_exposure",
                    mesh_id="D001205",
                    preferred_name="Ascorbic Acid",
                    match_type="synonym",
                    confidence=1,
                ),
            )
        }
    )
    plan = plan_adaptive_queries(c)
    assert any('"vitamin c"' in q.query and '"Ascorbic Acid"' in q.query for q in plan.queries)
    assert any(q.family == "endpoint" and "incidence" in q.query for q in plan.queries)
    assert len(plan.queries) <= 5


def test_single_digit_dose_or_duration_is_not_erased_from_scope():
    c = claim("Sleeping 9 hours", "daytime sleepiness")
    d = document(
        title="Sleeping 8 hours and daytime sleepiness",
        abstract="Sleeping 8 hours was associated with daytime sleepiness in adults.",
    )
    context = classify(c, d)
    assert context.classification == "related_indirect"
    assert "exposure:9" in context.missing_qualifiers
    assert '"9"' in plan_adaptive_queries(c).queries[0].query


def test_native_medlineplus_discovery_follows_one_verified_society_reference():
    async def run():
        nhs = "https://www.nhs.uk/conditions/example/"
        nlm = "https://medlineplus.gov/example.html"
        society = "https://www.aao.org/eye-health/example"
        text = "Synthetic clinical background on myopia for retrieval software testing only. " * 4
        called = []

        def handler(request):
            called.append(str(request.url))
            if request.url.host == "wsearch.nlm.nih.gov":
                return httpx.Response(200, text=f'<nlm><document url="{nlm}"/></nlm>')
            if request.url.path == "/search/results":
                return httpx.Response(200, text=f'<main><a href="{nhs}">A source</a></main>')
            if str(request.url) == nlm:
                return httpx.Response(
                    200,
                    text=f'<link rel="canonical" href="{nlm}"/>'
                    f'<div id="mplus-content"><div id="topic"><h1>Synthetic topic</h1>'
                    f'<p>{text}</p><a href="{society}">Published society reference</a></div></div>',
                )
            assert str(request.url) in {nhs, society}
            return httpx.Response(
                200,
                text=f'<link rel="canonical" href="{request.url}"/>'
                f"<main><h1>Synthetic source</h1><p>{text}</p></main>",
            )

        web = OfficialWebDiscovery(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        docs = await web.retrieve(claim(), "tablet myopia")
        assert len(docs) == 3 and len(called) == 5
        leaf = next(d for d in docs if d.canonical_url == society)
        assert leaf.metadata_provenance["discovered_by:official_link"] == nlm
        assert leaf.authoritative.currency == "unknown" and leaf.integrity.status == "unknown"
        assert classify(claim(), leaf).classification == "background_guidance"
        assert len([m for m in web.executions if m["operation"] == "document"]) == 3

    asyncio.run(run())
