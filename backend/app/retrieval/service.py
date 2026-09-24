"""PubMed-only retrieval orchestration, independent of API and persistence."""

from typing import Literal

from app.adapters.pubmed import PubMedAdapter
from app.retrieval.evidence_pack import build_evidence_pack, deduplicate_documents
from app.retrieval.models import (
    ClaimSnapshot,
    QueryExecution,
    RetrievalDiagnostics,
    RetrievalResult,
)
from app.retrieval.passages import extract_passages
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import rank_passages


async def retrieve_pubmed(claim: ClaimSnapshot, adapter: PubMedAdapter) -> RetrievalResult:
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
        for document in fetched if document.pmid in provenance
    ))
    missing = tuple(pmid for pmid in unique_pmids if pmid not in {d.pmid for d in documents})
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
    )
    return RetrievalResult(
        pack=build_evidence_pack(claim, plan, documents, ranked),
        diagnostics=diagnostics, query_executions=tuple(executions),
    )
