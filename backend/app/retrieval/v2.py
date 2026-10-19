"""Adaptive multi-provider discovery with canonical NCBI evidence hydration."""

import asyncio
import hashlib
import re
from collections import Counter
from dataclasses import asdict
from time import monotonic
from typing import Literal

from app.adapters.authoritative import AuthoritativeAdapter
from app.adapters.crossref import CrossrefAdapter
from app.adapters.discovery import DiscoveryLead, ScholarlyDiscovery
from app.adapters.official_web import OfficialWebDiscovery
from app.adapters.pubmed import PubMedAdapter
from app.adapters.source_metrics import source_http_metrics
from app.retrieval.adaptive import classify, discovery_terms, plan_adaptive_queries, scholarly_query
from app.retrieval.errors import RetrievalError
from app.retrieval.evidence_pack import build_evidence_pack, deduplicate_documents
from app.retrieval.integrity import merge_integrity, unavailable_crossref
from app.retrieval.models import (
    ClaimSnapshot,
    PubMedDocument,
    QueryExecution,
    RetrievalDiagnostics,
    RetrievalResult,
)
from app.retrieval.passages import extract_passages
from app.retrieval.ranking import rank_passages
from app.retrieval.service import _enrich_dois
from app.retrieval.study_quality import annotate_study_quality


def identity_matches(lead: DiscoveryLead, doc: PubMedDocument) -> bool:
    """An identifier lead cannot relabel another publication's frozen content."""

    def title(value: str) -> str:
        return re.sub(r"\W+", "", value.casefold())

    return bool(
        lead.pmid == doc.pmid
        and title(lead.title) == title(doc.title)
        and (not lead.doi or bool(doc.doi and lead.doi.casefold() == doc.doi.casefold()))
    )


async def _retrieve_adaptive(
    claim: ClaimSnapshot,
    adapter: PubMedAdapter,
    *,
    discovery: ScholarlyDiscovery,
    web: OfficialWebDiscovery | None = None,
    authoritative: AuthoritativeAdapter | None = None,
    crossref: CrossrefAdapter | None = None,
    selected_limit: int = 8,
    max_per_document: int = 1,
    crossref_total_timeout_seconds: float = 30,
) -> RetrievalResult:
    started = monotonic()
    plan = plan_adaptive_queries(claim)
    executions = []
    query_metrics: list[dict[str, object]] = []
    provenance: dict[str, set[str]] = {}
    leads: list[DiscoveryLead] = []
    reasons: Counter[str] = Counter()
    source_statuses: dict[str, str] = {}

    async def public_sources() -> tuple[PubMedDocument, ...]:
        if web:
            return await web.retrieve(claim, discovery_terms(claim, broad=True))
        return ()

    async def approved_sources() -> tuple[PubMedDocument, ...]:
        if authoritative:
            docs, statuses = await authoritative.retrieve(claim)
            source_statuses.update(statuses)
            return docs
        return ()

    async def scholarly(broad: bool) -> None:
        if not discovery_terms(claim, broad=broad):
            return
        found = await asyncio.gather(
            *(
                discovery.search(provider, scholarly_query(claim, broad=broad, provider=provider))
                for provider in ("europe_pmc", "openalex")
            )
        )
        for batch in found:
            for lead in batch:
                leads.append(lead)
                if lead.pmid and lead.publication_type != "retracted":
                    provenance.setdefault(lead.pmid, set()).add("discovery:" + lead.provider)

    async def searches() -> None:
        # PubMed requests retain the global NCBI throttle. Other providers run
        # concurrently; mutable last_search_diagnostics is never read in a race.
        for query in plan.queries:
            # At least the full and core searches; design query only on low recall.
            if (
                query.family == "relation"
                and any(q.family == "mesh" for q in plan.queries)
                and len(provenance) >= 20
            ):
                continue
            tick = monotonic()
            status = "ok"
            try:
                ids, hit = await adapter.search(query.query)
                details = dict(getattr(adapter, "last_search_diagnostics", {}))
            except RetrievalError as exc:
                ids, hit, details = (), False, {}
                status = exc.kind
                reasons["pubmed_search_" + exc.kind] += 1
            executions.append(
                QueryExecution(query_id=query.query_id, pmids=ids, cache_hit=hit, **details)
            )
            query_metrics.append(
                {
                    "provider": "pubmed",
                    "query_id": query.query_id,
                    "status": status,
                    "latency_ms": round((monotonic() - tick) * 1000),
                    "cache_hit": hit,
                    "returned": len(ids),
                    "started_monotonic_ms": round(tick * 1000),
                    "finished_monotonic_ms": round(monotonic() * 1000),
                }
            )
            for pmid in ids:
                provenance.setdefault(pmid, set()).add(query.query_id)

    async def scholarly_stages() -> None:
        await scholarly(False)
        if discovery_terms(claim, broad=False) != discovery_terms(claim, broad=True):
            await scholarly(True)

    # TaskGroup cancels children on parent deadline/error; no orphan source work.
    async with asyncio.TaskGroup() as group:
        web_task = group.create_task(public_sources())
        approved_task = group.create_task(approved_sources())
        group.create_task(scholarly_stages())
        group.create_task(searches())
    # Keep first hits across providers; PubMed anchors precede supplementary IDs.
    pmids = tuple(
        sorted(
            provenance,
            key=lambda p: (
                not any(q.startswith("Q") for q in provenance[p]),
                list(provenance).index(p),
            ),
        )
    )[:40]
    if len(provenance) > len(pmids):
        reasons["candidate_budget_omitted"] = len(provenance) - len(pmids)
    fetch_started = monotonic()
    try:
        fetched = await adapter.fetch_cached(pmids)
        documents = tuple(d for d in fetched.documents if d.pmid in pmids)
        reasons["unrequested_canonical_record_excluded"] += len(fetched.documents) - len(documents)
        missing = tuple(p for p in pmids if p not in {d.pmid for d in documents})
    except RetrievalError as exc:
        documents, missing = (), pmids
        reasons["canonical_fetch_" + exc.kind] += 1
    query_metrics.append(
        {
            "provider": "pubmed",
            "operation": "fetch",
            "status": "ok" if not missing else "partial_or_failed",
            "latency_ms": round((monotonic() - fetch_started) * 1000),
            "requested": len(pmids),
            "returned": len(documents),
            "cache_hit": getattr(adapter, "last_fetch_cache_hit", False),
        }
    )
    verified = []
    lead_audit = []
    for lead in leads:
        doc = next((d for d in documents if d.pmid == lead.pmid), None)
        verification_status = (
            "excluded_retracted_discovery"
            if lead.publication_type == "retracted"
            else "no_canonical_pmid_content"
            if not doc
            else "verified_ncbi_identity"
            if identity_matches(lead, doc)
            else "identity_mismatch"
        )
        lead_audit.append({**asdict(lead), "verification": verification_status})
        reasons[verification_status] += 1
    for doc in documents:
        matching = tuple(
            lead
            for lead in leads
            if identity_matches(lead, doc) and lead.publication_type != "retracted"
        )
        # A bad supplementary record cannot suppress an independently found NCBI
        # record. But it cannot add discovery provenance or enter on its own.
        query_ids = tuple(sorted(q for q in provenance[doc.pmid] if q.startswith("Q")))
        if not query_ids and not matching:
            reasons["unverified_discovery_excluded"] += 1
            continue
        metadata = {
            **doc.metadata_provenance,
            **{"discovered_by:" + lead.provider: lead.identifier for lead in matching},
            **{
                "discovery_query:"
                + lead.provider
                + ":"
                + hashlib.sha256(lead.query.encode()).hexdigest(): lead.query
                for lead in matching
                if lead.query
            },
        }
        verified.append(
            doc.model_copy(update={"query_ids": query_ids, "metadata_provenance": metadata})
        )
    documents = deduplicate_documents(tuple(verified))
    enrich_started = monotonic()
    relevant_documents = tuple(
        d for d in documents if classify(claim, d).classification != "irrelevant"
    )
    enrichments = await _enrich_dois(
        relevant_documents, crossref, timeout_seconds=crossref_total_timeout_seconds
    )
    documents = tuple(
        annotate_study_quality(
            claim,
            d.model_copy(
                update={
                    "crossref": enrichments.get(d.document_id, unavailable_crossref(d.doi)),
                    "integrity": merge_integrity(
                        d, enrichments.get(d.document_id, unavailable_crossref(d.doi))
                    ),
                }
            ),
        )
        for d in documents
    )
    query_metrics.append(
        {
            "provider": "crossref",
            "operation": "enrichment",
            "latency_ms": round((monotonic() - enrich_started) * 1000),
            "requested": sum(bool(d.doi) for d in relevant_documents) if crossref else 0,
        }
    )
    documents = deduplicate_documents((*documents, *approved_task.result(), *web_task.result()))
    passages = tuple(p for doc in documents for p in extract_passages(doc))
    ranked = rank_passages(claim, documents, passages)
    if (
        missing
        or any(
            m.get("status") not in {"ok", None}
            for m in query_metrics
            if m.get("provider") == "pubmed"
        )
        or any(m.get("status") == "failed" for m in discovery.executions)
        or any(m.get("status") == "failed" for m in (web.executions if web else []))
    ):
        plan = plan.model_copy(
            update={"warnings": (*plan.warnings, "retrieval_v2_provider_partial_failure")}
        )
    pack = build_evidence_pack(
        claim,
        plan,
        documents,
        ranked,
        selected_limit=selected_limit,
        max_per_document=max_per_document,
        pack_version="2.0",
    )
    # Every planned query has an execution record, including bounded skipped queries.
    executed = {e.query_id for e in executions}
    plan = plan.model_copy(
        update={"queries": tuple(q for q in plan.queries if q.query_id in executed)}
    )
    if plan != pack.query_plan:
        pack = build_evidence_pack(
            claim,
            plan,
            documents,
            ranked,
            selected_limit=selected_limit,
            max_per_document=max_per_document,
            pack_version="2.0",
        )
    successful = sum(
        m.get("status") == "ok" for m in query_metrics if m.get("operation") != "fetch"
    ) + sum(m.get("status") == "ok" for m in discovery.executions)
    failed = any(
        m.get("status") not in {"ok", None} for m in query_metrics if m.get("provider") == "pubmed"
    )
    status: Literal["ok", "no_results", "partial_metadata", "failed"] = (
        "partial_metadata"
        if missing
        else "failed"
        if not documents and not successful
        else "partial_metadata"
        if not pack.selected_evidence_ids and failed
        else "no_results"
        if not documents
        else "ok"
    )
    counts = Counter(
        d.retrieval_context.classification for d in pack.documents if d.retrieval_context
    )
    adaptive = {
        "version": "retrieval-v2.0",
        "elapsed_ms": round((monotonic() - started) * 1000),
        "classification_counts": dict(counts),
        "provider_executions": [
            *query_metrics,
            *discovery.executions,
            *(web.executions if web else []),
        ],
        "discovery_leads": lead_audit,
        "model_calls": 0,
        "cost": {
            "currency": "USD",
            "known_charge": 0,
            "basis": "public/anonymous endpoints; provider billing not exposed",
        },
        "coverage": "direct_candidates"
        if counts["direct"]
        else "related_only"
        if (counts["related_indirect"] or counts["background_guidance"])
        else "none",
        "limits": {
            "pubmed_queries": 5,
            "discovery_searches_per_provider": 2,
            "canonical_documents": 40,
            "web_searches": 2,
            "web_pages": 3,
            "context_selected_documents": 2,
        },
    }
    diagnostics = RetrievalDiagnostics(
        status=status,
        query_count=len(executions),
        cache_hits=sum(e.cache_hit for e in executions),
        pmids_found=len(provenance),
        documents_returned=len(documents),
        missing_pmids=missing,
        warnings=tuple(f"{k}:{v}" for k, v in reasons.items() if "excluded" in k or "fetch_" in k),
        reason_counts=dict(reasons),
        search_executions=tuple(executions),
        authoritative_statuses=source_statuses,
        integrity_status_counts=dict(Counter(d.integrity.status for d in pack.documents)),
        crossref_status_counts=dict(
            Counter(d.crossref.check.status for d in pack.documents if d.crossref)
        ),
        doi_coverage=sum(bool(d.doi) for d in pack.documents),
        adaptive=adaptive,
    )
    return RetrievalResult(pack=pack, diagnostics=diagnostics, query_executions=tuple(executions))


async def retrieve_adaptive(
    claim: ClaimSnapshot,
    adapter: PubMedAdapter,
    *,
    discovery: ScholarlyDiscovery,
    web: OfficialWebDiscovery | None = None,
    authoritative: AuthoritativeAdapter | None = None,
    crossref: CrossrefAdapter | None = None,
    selected_limit: int = 8,
    max_per_document: int = 1,
    crossref_total_timeout_seconds: float = 30,
) -> RetrievalResult:
    with source_http_metrics() as counts:
        result = await _retrieve_adaptive(
            claim,
            adapter,
            discovery=discovery,
            web=web,
            authoritative=authoritative,
            crossref=crossref,
            selected_limit=selected_limit,
            max_per_document=max_per_document,
            crossref_total_timeout_seconds=crossref_total_timeout_seconds,
        )
    audit = {
        **(result.diagnostics.adaptive or {}),
        "source_http_requests": dict(counts),
        "source_http_request_count": sum(counts.values()),
    }
    return result.model_copy(
        update={"diagnostics": result.diagnostics.model_copy(update={"adaptive": audit})}
    )
