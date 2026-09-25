"""PubMed-only retrieval orchestration, independent of API and persistence."""

import asyncio
from collections import Counter
from typing import Literal

from app.adapters.crossref import CrossrefAdapter
from app.adapters.pubmed import PubMedAdapter
from app.retrieval.evidence_pack import build_evidence_pack, deduplicate_documents
from app.retrieval.integrity import failed_crossref, merge_integrity, unavailable_crossref
from app.retrieval.models import (
    ClaimSnapshot,
    CrossrefEnrichment,
    PubMedDocument,
    QueryExecution,
    RetrievalDiagnostics,
    RetrievalResult,
)
from app.retrieval.passages import extract_passages
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import rank_passages
from app.retrieval.study_quality import annotate_study_quality


async def retrieve_pubmed(
    claim: ClaimSnapshot, adapter: PubMedAdapter, *,
    selected_limit: int = 8, max_per_document: int = 1,
    crossref: CrossrefAdapter | None = None,
    crossref_total_timeout_seconds: float = 30,
) -> RetrievalResult:
    """Retrieve a bounded source set and freeze it without asserting a verdict."""

    plan = plan_pubmed_queries(claim)
    executions: list[QueryExecution] = []
    provenance: dict[str, set[str]] = {}
    for query in plan.queries:
        pmids, cache_hit = await adapter.search(query.query)
        executions.append(QueryExecution(
            query_id=query.query_id, pmids=pmids, cache_hit=cache_hit,
        ))
        for pmid in pmids:
            provenance.setdefault(pmid, set()).add(query.query_id)
    unique_pmids = tuple(sorted(provenance, key=lambda value: int(value)))
    fetched = await adapter.fetch(unique_pmids)
    documents = deduplicate_documents(tuple(
        document.model_copy(update={"query_ids": tuple(sorted(provenance[document.pmid]))})
        for document in fetched.documents if document.pmid in provenance
    ))
    missing = tuple(pmid for pmid in unique_pmids if pmid not in {d.pmid for d in documents})
    missing_records = set(unique_pmids) - set(fetched.seen_pmids)
    reasons: Counter[str] = Counter()
    reasons["missing_efetch_record"] = len(missing_records)
    reasons["incomplete_efetch_record"] = len(set(fetched.incomplete_pmids) & set(unique_pmids))
    reasons["unsupported_efetch_record_type"] = len(
        set(fetched.unsupported_pmids) & set(unique_pmids)
    )
    crossref_results = await _enrich_dois(
        documents, crossref, timeout_seconds=crossref_total_timeout_seconds,
    )
    enriched = []
    for document in documents:
        if document.doi:
            enrichment = crossref_results[document.document_id]
        else:
            enrichment = unavailable_crossref(None)
            reasons["optional_doi_absent"] += 1
            reasons["crossref_not_applicable"] += 1
        if document.abstract is None:
            reasons["optional_abstract_absent"] += 1
        if document.publication_date is None:
            reasons["incomplete_publication_date"] += 1
        if enrichment.check.status == "failed":
            reasons["crossref_lookup_failed"] += 1
        elif enrichment.check.status == "not_found":
            reasons["crossref_not_found"] += 1
        elif enrichment.check.status == "unavailable":
            reasons["integrity_source_unavailable"] += 1
        integrity = merge_integrity(document, enrichment)
        if any(check.status == "unavailable" for check in document.integrity.checks):
            reasons["integrity_source_unavailable"] += 1
        provenance_fields = dict(document.metadata_provenance)
        if enrichment.check.failure_type == "doi_mismatch":
            provenance_fields["doi_comparison"] = "crossref_mismatch_rejected"
        if enrichment.check.status == "checked":
            provenance_fields["crossref_work_type"] = "crossref"
            provenance_fields["crossref_publisher"] = "crossref"
            provenance_fields["crossref_published_date"] = "crossref"
            if document.publication_date and enrichment.published_date:
                provenance_fields["publication_date_comparison"] = (
                    "agrees" if document.publication_date == enrichment.published_date
                    else "disagrees_preserved_both"
                )
        enriched.append(annotate_study_quality(claim, document.model_copy(update={
            "crossref": enrichment, "integrity": integrity,
            "metadata_provenance": provenance_fields,
        })))
    documents = tuple(enriched)
    status: Literal["ok", "no_results", "partial_metadata"] = (
        "partial_metadata" if missing else "no_results" if not documents else "ok"
    )
    passages = tuple(passage for document in documents for passage in extract_passages(document))
    ranked = rank_passages(claim, documents, passages)
    diagnostics = RetrievalDiagnostics(
        status=status, query_count=len(plan.queries),
        cache_hits=sum(execution.cache_hit for execution in executions),
        pmids_found=len(unique_pmids), documents_returned=len(documents),
        missing_pmids=missing,
        warnings=(("partial_pubmed_metadata",) if missing else ()),
        reason_counts={key: count for key, count in sorted(reasons.items()) if count},
        integrity_status_counts=dict(sorted(Counter(
            document.integrity.status for document in documents
        ).items())),
        crossref_status_counts=dict(sorted(Counter(
            document.crossref.check.status for document in documents if document.crossref
        ).items())),
        doi_coverage=sum(document.doi is not None for document in documents),
    )
    return RetrievalResult(
        pack=build_evidence_pack(
            claim, plan, documents, ranked,
            selected_limit=selected_limit, max_per_document=max_per_document,
        ),
        diagnostics=diagnostics, query_executions=tuple(executions),
    )


async def _enrich_dois(
    documents: tuple[PubMedDocument, ...], crossref: CrossrefAdapter | None, *,
    timeout_seconds: float,
) -> dict[str, CrossrefEnrichment]:
    doi_documents = tuple(document for document in documents if document.doi)
    if crossref is None:
        return {document.document_id: unavailable_crossref(document.doi)
                for document in doi_documents}
    semaphore = asyncio.Semaphore(3)

    async def check(document: PubMedDocument) -> CrossrefEnrichment:
        assert document.doi is not None
        async with semaphore:
            return await crossref.enrich(document.doi)

    tasks = {document.document_id: asyncio.create_task(check(document))
             for document in doi_documents}
    if not tasks:
        return {}
    done, pending = await asyncio.wait(tasks.values(), timeout=timeout_seconds)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    results: dict[str, CrossrefEnrichment] = {}
    for document in doi_documents:
        task = tasks[document.document_id]
        if task in done:
            try:
                results[document.document_id] = task.result()
                continue
            except Exception:
                results[document.document_id] = failed_crossref(document.doi or "", "adapter")
        else:
            results[document.document_id] = failed_crossref(document.doi or "", "deadline")
    return results
