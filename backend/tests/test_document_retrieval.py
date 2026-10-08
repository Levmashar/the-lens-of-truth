"""Shared retrieval keeps study identity, endpoint coverage and citation ownership distinct."""

import asyncio
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.adapters.authoritative import ApprovedSource, AuthoritativeAdapter, SourceManifest
from app.adapters.pmc import PmcFullText, PmcFullTextAdapter, parse_pmc_xml
from app.document.models import DocumentAssertion, DocumentGroup, DocumentPlan, SourceSpan
from app.document.retrieval import (
    DocumentSourceCache,
    GroupEvidenceSnapshot,
    _source_match,
    document_claim_snapshots,
    document_normalization_audit,
    plan_group_queries,
    retrieve_document_group,
)
from app.judging.prompt import prepare_judge_input
from app.medical.linker import MedicalEntityLinker
from app.medical.mesh import LocalMeshProvider
from app.medical.umls import UnconfiguredUmlsProvider
from app.pipeline.pico import NormalizedPico
from app.retrieval.errors import RetrievalError
from app.retrieval.models import (
    AbstractSection,
    DocumentIntegrity,
    IntegrityCheck,
    PubMedDocument,
    PubMedFetchResult,
)
from app.retrieval.passages import extract_passages


def _document(pmid="100", title="Example Biobank cohort research", abstract=None):
    abstract = abstract or (
        "Example Biobank included 500 participants. Exposure X use was associated with "
        "increased endpoint Y and endpoint Z. The association was not a causal conclusion."
    )
    return PubMedDocument(
        document_id=f"pubmed:{pmid}",
        pmid=pmid,
        title=title,
        abstract=abstract,
        abstract_sections=(AbstractSection(label="RESULTS", text=abstract),),
        canonical_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        retrieved_at=datetime.now(UTC),
        content_sha256=hashlib.sha256(abstract.encode()).hexdigest(),
        integrity=DocumentIntegrity(
            checks=(
                IntegrityCheck(
                    source="pubmed",
                    status="checked",
                    version="fixture",
                ),
            )
        ),
    )


def _plan():
    sentences = (
        "Example Biobank reported an association between exposure X and endpoint Y.",
        "It also reported an association with endpoint Z.",
    )
    original = " ".join(sentences)
    spans = []
    offset = 0
    for sentence in sentences:
        spans.append(SourceSpan(start=offset, end=offset + len(sentence), text=sentence))
        offset += len(sentence) + 1
    assertions = tuple(
        DocumentAssertion(
            assertion_id=f"A{i}",
            ordinal=i,
            kind="reported_study_fact",
            spans=(span,),
            normalized_text=span.text,
            pico=NormalizedPico(
                original_claim=span.text,
                intervention_or_exposure="exposure X",
                outcome="endpoint Y" if i == 1 else "endpoint Z",
                claim_type="association",
            ),
        )
        for i, span in enumerate(spans, 1)
    )
    group = DocumentGroup(
        group_id="G1",
        title="Example research",
        assertion_ids=("A1", "A2"),
        study_clues=(spans[0],),
        context_spans=tuple(spans),
    )
    return DocumentPlan(
        original_text=original,
        original_sha256=hashlib.sha256(original.encode()).hexdigest(),
        assertions=assertions,
        groups=(group,),
    )


def test_commentary_does_not_count_toward_the_approved_source_assertion_bound():
    base = _plan()
    text = base.original_text
    assertions = list(base.assertions)
    for index in range(3, 13):
        comment = f"Discussion note {index}."
        start = len(text) + 1
        text += " " + comment
        assertions.append(
            DocumentAssertion(
                assertion_id=f"A{index}",
                ordinal=index,
                kind="commentary",
                spans=(SourceSpan(start=start, end=len(text), text=comment),),
                normalized_text=comment,
                pico=NormalizedPico(original_claim=comment),
                planning_status="not_checkable",
            )
        )
    document = DocumentPlan(
        original_text=text,
        original_sha256=hashlib.sha256(text.encode()).hexdigest(),
        assertions=tuple(assertions),
        groups=(
            base.groups[0].model_copy(
                update={
                    "assertion_ids": tuple(a.assertion_id for a in assertions),
                }
            ),
        ),
    )

    class Approved:
        async def retrieve_group(self, claims, *, document_cache):
            assert len(claims) == 2
            assert {c.raw_text for c in claims} == {a.source_text for a in base.assertions}
            return (), {}

    result = asyncio.run(
        retrieve_document_group(
            uuid4(),
            document,
            document.groups[0],
            _PubMed(),
            authoritative=Approved(),
        )
    )
    assert len(result.claim_snapshots) == 12
    assert all(not result.per_assertion_evidence_ids[f"A{i}"] for i in range(3, 13))


class _PubMed:
    last_search_diagnostics = {}

    def __init__(self):
        self.searches = []
        self.fetches = []

    async def search(self, query):
        self.searches.append(query)
        return ("100",), False

    async def fetch(self, pmids):
        self.fetches.append(pmids)
        return PubMedFetchResult(documents=(_document(),))


class _FullText:
    discovery_requests = 0

    def __init__(self):
        self.fetches = []

    async def discover(self, query):
        self.discovery_requests += 1
        return ("100",)

    async def fetch(self, document):
        self.fetches.append(document.pmid)
        return PmcFullText(
            document_id=document.document_id,
            pmid=document.pmid,
            pmcid="PMC900",
            status="available",
            retrieved_at=datetime.now(UTC),
            passages=extract_passages(document),
            source_requests=2,
        )


def test_group_retrieves_each_publication_once_and_freezes_one_catalog():
    plan = _plan()
    pubmed = _PubMed()
    fulltext = _FullText()
    result = asyncio.run(
        retrieve_document_group(
            uuid4(),
            plan,
            plan.groups[0],
            pubmed,
            fulltext=fulltext,
        )
    )

    assert pubmed.fetches == [("100",)]
    assert fulltext.fetches == ["100"]
    assert set(result.per_assertion_evidence_ids) == {"A1", "A2"}
    assert all(result.per_assertion_evidence_ids.values())
    assert len(result.source_units) == len(result.pack.selected_evidence_ids)
    assert len({u.unit_id for u in result.source_units}) == len(result.source_units)
    assert result.source_match.status == "identified"
    assert result.source_match.matched_document_ids == ("pubmed:100",)
    assert result.source_fetches["pubmed_fetch_batches"] == 1
    # These fixtures implement source operations without any HTTP send.
    assert result.source_http_requests == {}
    assert result.metrics["source_http_request_count"] == 0
    assert result.source_fetches["crossref_enrichment_calls"] == 0
    assert result.candidate_pmids == ("100",)
    assert len(result.query_executions) == len(result.pack.query_plan.queries)
    assert result.normalization_status == {"A1": "not_applicable", "A2": "not_applicable"}
    assert all(result.normalization_ready.values())
    GroupEvidenceSnapshot.model_validate(result.model_dump(mode="json"))


def test_document_retrieval_fetches_one_approved_source_for_both_assertions():
    plan = _plan()
    attempts = 0
    source = ApprovedSource(
        source_id="fixture-nci",
        organization="NCI",
        canonical_url="https://www.cancer.gov/fixture",
        document_title="Synthetic shared cohort source",
        document_purpose="research_report",
        topic_terms=("association",),
        root_attribute="id",
        root_value="evidence",
        last_verified_at=datetime.now(UTC),
        retrieval_method="html_blocks",
        independence_group="fixture-body",
        attribution="Synthetic fixture.",
    )
    html = (
        '<main id="evidence"><p>Example Biobank studied exposure X and found endpoint Y.</p>'
        "<p>The same cohort found endpoint Z in the measured participants.</p></main>"
        f'<time datetime="{datetime.now(UTC).date().isoformat()}">Updated</time>'
    )

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            approved = AuthoritativeAdapter(
                SourceManifest(version="fixture", sources=(source,)), client=client
            )
            return await retrieve_document_group(
                uuid4(),
                plan,
                plan.groups[0],
                _PubMed(),
                authoritative=approved,
            )

    result = asyncio.run(run())

    assert attempts == 1
    assert result.source_http_requests == {"authoritative.document": 1}
    assert result.metrics["source_http_request_count"] == 1
    assert result.source_fetches["authoritative_sources_considered"] == 1
    assert any("endpoint Z" in p.text for p in result.retrieved_passages)
    assert not any("Approved source fixture-nci: current" in text for text in result.limitations)


def test_existing_judge_input_uses_exactly_the_shared_catalog_without_hidden_context():
    plan = _plan()
    result = asyncio.run(retrieve_document_group(uuid4(), plan, plan.groups[0], _PubMed()))

    prepared = prepare_judge_input(uuid4(), result.pack, version="judge-input-2.5")

    assert set(prepared.input_snapshot_json["judge_visible_evidence_ids"]) == set(
        result.pack.selected_evidence_ids
    )
    assert prepared.input_snapshot_json["source_units"] == [
        u.model_dump(mode="json") for u in result.source_units
    ]
    assert prepared.input_snapshot_json["source_quantity_catalog"] == (
        result.source_quantity_catalog
    )


def test_clinical_and_interpretation_normalization_preserve_existing_readiness_gate():
    sentences = (
        "Smoking causes lung cancer.",
        "This treatment changes health.",
        "The study included 500 people.",
    )
    original = " ".join(sentences)
    spans = []
    offset = 0
    for sentence in sentences:
        spans.append(SourceSpan(start=offset, end=offset + len(sentence), text=sentence))
        offset += len(sentence) + 1
    assertions = tuple(
        DocumentAssertion(
            assertion_id=f"A{i}",
            ordinal=i,
            kind=kind,
            spans=(span,),
            normalized_text=span.text,
            pico=NormalizedPico(
                original_claim=span.text,
                claim_type="causal",
                intervention_or_exposure="Smoking" if i == 1 else "treatment" if i == 2 else None,
                outcome="lung cancer" if i < 3 else None,
            ),
        )
        for i, (span, kind) in enumerate(
            zip(
                spans,
                (
                    "general_medical_assertion",
                    "interpretation",
                    "sample_size",
                ),
                strict=True,
            ),
            1,
        )
    )
    group = DocumentGroup(
        group_id="G1",
        title="Clinical readiness",
        assertion_ids=(
            "A1",
            "A2",
            "A3",
        ),
        context_spans=tuple(spans),
    )
    plan = DocumentPlan(
        original_text=original,
        original_sha256=hashlib.sha256(original.encode()).hexdigest(),
        assertions=assertions,
        groups=(group,),
    )
    linker = MedicalEntityLinker(
        UnconfiguredUmlsProvider(),
        LocalMeshProvider(
            {
                "Smoking": ("D012907", "Smoking", 1.0),
                "lung cancer": ("D008175", "Lung Neoplasms", 1.0),
            }
        ),
    )

    snapshots = document_claim_snapshots(uuid4(), plan, group, linker)
    statuses, qualities, readiness = document_normalization_audit(plan, group, snapshots, linker)

    assert statuses == {"A1": "normalized", "A2": "partial", "A3": "not_applicable"}
    assert readiness == {"A1": True, "A2": False, "A3": True}
    assert snapshots["A2"].pico.outcome is None
    assert qualities["A2"].required_slots_missing == ("outcome",)
    assert qualities["A3"].required_slots_missing == ()

    no_linker_snapshots = document_claim_snapshots(uuid4(), plan, group)
    _, no_linker_quality, no_linker_readiness = document_normalization_audit(
        plan,
        group,
        no_linker_snapshots,
    )
    assert not no_linker_readiness["A1"]
    assert "source_terminology_scan_unavailable" in no_linker_quality["A1"].normalization_warnings


def test_one_analysis_reuses_publications_integrity_and_fulltext_without_verdict_cache():
    plan = _plan()
    pubmed = _PubMed()
    fulltext = _FullText()
    cache = DocumentSourceCache()
    analysis_id = uuid4()

    async def run():
        first = await retrieve_document_group(
            analysis_id,
            plan,
            plan.groups[0],
            pubmed,
            fulltext=fulltext,
            source_cache=cache,
        )
        second = await retrieve_document_group(
            analysis_id,
            plan,
            plan.groups[0],
            pubmed,
            fulltext=fulltext,
            source_cache=cache,
        )
        return first, second

    first, second = asyncio.run(run())

    assert len(pubmed.fetches) == 1
    assert len(fulltext.fetches) == 1
    assert first.pack.selected_evidence_ids == second.pack.selected_evidence_ids
    assert second.source_fetches["publication_reuse_hits"] == 1
    assert second.source_fetches["pmc_cache_or_reuse_hits"] == 1


def test_topical_similarity_or_a_contrary_trial_cannot_identify_the_attributed_study():
    plan = _plan()
    doc = _document(
        title="Randomized exposure X trial",
        abstract=("Exposure X reduces endpoint Y and endpoint Z in a randomized trial."),
    )
    passages = extract_passages(doc)
    snapshots = document_claim_snapshots(uuid4(), plan, plan.groups[0])

    result = _source_match(plan.groups[0], snapshots, (doc,), passages, {})

    assert result.status == "uncertain"
    assert result.matched_document_ids == ()
    assert not result.candidates[0].identity_established


def test_two_different_matching_studies_stay_uncertain_instead_of_forcing_identity():
    plan = _plan()
    documents = (_document("100"), _document("101"))
    passages = tuple(p for doc in documents for p in extract_passages(doc))

    result = _source_match(
        plan.groups[0],
        document_claim_snapshots(uuid4(), plan, plan.groups[0]),
        documents,
        passages,
        {},
    )

    assert result.status == "uncertain"
    assert result.matched_document_ids == ()
    assert len(result.candidates) == 2


def test_source_clue_and_each_distinct_endpoint_are_present_in_query_union():
    plan = _plan()
    snapshots = document_claim_snapshots(uuid4(), plan, plan.groups[0])

    queries, _ = plan_group_queries(plan.groups[0], snapshots)

    assert any('"Example Biobank"' in q.query for q in queries.queries)
    assert any('"endpoint Z"' in q.query for q in queries.queries)
    assert len({q.query for q in queries.queries}) == len(queries.queries)


def test_group_quantity_or_unit_mutation_is_rejected():
    plan = _plan()
    result = asyncio.run(retrieve_document_group(uuid4(), plan, plan.groups[0], _PubMed()))
    raw = result.model_dump(mode="json")
    raw["source_units"][0]["text"] += " fabricated"

    with pytest.raises(ValueError, match="ownership"):
        GroupEvidenceSnapshot.model_validate(raw)


PMC_XML = b"""<pmc-articleset><article><front><article-meta>
<article-id pub-id-type="pmid">100</article-id><article-id pub-id-type="pmcaid">PMC900</article-id>
</article-meta></front><body>
<sec><title>Materials and Methods</title><p>The cohort included 500 participants.</p></sec>
<sec><title>Results</title><p>Exposure X was associated with endpoint Y.</p>
<table-wrap id="T1"><label>Table 1</label><caption><p>Observed outcomes</p></caption>
<table><thead><tr><th>Exposure</th><th>OR (95% CI)</th></tr></thead>
<tbody><tr><td>Always</td><td>3.92 (2.5-4.5)</td></tr></tbody></table>
<table-wrap-foot><fn><p>Reference: never. Crude association, not an adjusted estimate.</p></fn>
</table-wrap-foot></table-wrap></sec></body></article></pmc-articleset>"""


def test_pmc_preserves_methods_table_headers_reference_and_footnotes():
    result = parse_pmc_xml(PMC_XML, _document(), "PMC900")

    assert result.status == "available"
    table = next(p for p in result.passages if "/TABLE/" in p.section)
    assert "OR (95% CI)" in table.text
    assert "3.92 (2.5-4.5)" in table.text
    assert "Reference: never." in table.text
    assert "not an adjusted estimate" in table.text
    assert "292%" not in table.text
    assert result.locations[table.passage_id].endswith("table-wrap[1]")
    assert any("Methods" in p.section for p in result.passages)


@pytest.mark.parametrize(
    "changed",
    [
        PMC_XML.replace(b">100<", b">999<"),
        PMC_XML.replace(b"PMC900", b"PMC901"),
    ],
)
def test_pmc_parent_identity_mismatch_never_supplies_findings(changed):
    result = parse_pmc_xml(changed, _document(), "PMC900")

    assert result.status == "identity_mismatch"
    assert result.passages == ()


def test_pmc_inaccessible_body_records_limitation_without_inventing_results():
    result = parse_pmc_xml(
        PMC_XML.split(b"<body>")[0] + b"</article></pmc-articleset>", _document(), "PMC900"
    )

    assert result.status == "metadata_only"
    assert result.passages == ()
    assert result.limitations


@pytest.mark.parametrize(
    "payloads",
    [
        ({"esearchresult": {"idlist": "invalid"}},),
        ({"esearchresult": {"idlist": ["900"]}}, {"linksets": ["invalid"]}),
        ({"esearchresult": {"idlist": ["900"]}}, {"linksets": None}),
    ],
)
def test_pmc_discovery_malformed_response_is_a_bounded_source_failure(payloads):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class PubMed:
        def __init__(self):
            self.pending = iter(payloads)

        async def _request(self, endpoint, params):
            return Response(next(self.pending))

    adapter = PmcFullTextAdapter(PubMed())

    with pytest.raises(RetrievalError) as failure:
        asyncio.run(adapter.discover('"Example Biobank"[All Fields]'))

    assert failure.value.kind == "malformed_response"
