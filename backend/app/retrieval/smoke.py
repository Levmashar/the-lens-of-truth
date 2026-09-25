"""Live, explicit PubMed smoke check for an existing normalized claim.

Run for a stored claim UUID, or pass explicit source-grounded PICO fields.
"""

import argparse
import asyncio
from uuid import UUID, uuid4

from app.adapters.crossref import CrossrefAdapter
from app.adapters.pubmed import PubMedAdapter, RedisQueryCache
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.dependencies import build_entity_linker
from app.models.claim import Claim
from app.pipeline.claim_types import ClaimType, explicit_relation
from app.pipeline.pico import normalize_stored_pico
from app.retrieval.claims import snapshot_claim
from app.retrieval.models import ClaimSnapshot
from app.retrieval.persistence import persist_retrieval
from app.retrieval.service import retrieve_pubmed


async def smoke(
    source: str, *, exposure: str | None, outcome: str | None,
    claim_type: ClaimType | None,
) -> None:
    settings = get_settings()
    if not settings.ncbi_email:
        raise SystemExit("Set NCBI_EMAIL to a real developer contact before live PubMed use.")
    try:
        claim_id = UUID(source)
    except ValueError:
        if not exposure or not outcome or claim_type is None:
            raise SystemExit(
                "For raw text, provide --exposure, --outcome, and --claim-type."
            ) from None
        stated_relation = explicit_relation(source)
        if stated_relation is not None and stated_relation != claim_type:
            raise SystemExit("Claim type conflicts with explicit source wording.") from None
        pico = normalize_stored_pico(
            raw_text=source, claim_type=claim_type,
            population=None, intervention_or_exposure=exposure,
            comparator=None, outcome=outcome, timeframe=None,
        )
        if not pico.intervention_or_exposure or not pico.outcome:
            raise SystemExit("Exposure and outcome must occur in the source text.") from None
        snapshot = ClaimSnapshot(
            claim_id=uuid4(), raw_text=source, claim_type=claim_type,
            pico=pico, entities=build_entity_linker(settings).link(pico),
        )
        persist = False
    else:
        with SessionLocal() as session:
            claim = session.get(Claim, claim_id)
            if claim is None:
                raise SystemExit("Claim was not found; create an analysis first.")
            snapshot = snapshot_claim(claim)
        persist = True
    key = settings.ncbi_api_key
    adapter = PubMedAdapter(
        tool=settings.ncbi_tool, email=settings.ncbi_email,
        api_key=key.get_secret_value() if key else None,
        timeout_seconds=settings.pubmed_timeout_seconds,
        max_retries=settings.pubmed_max_retries,
        minimum_interval_seconds=0.36,
        retmax=settings.pubmed_query_retmax,
        cache=RedisQueryCache(settings.redis_url),
        cache_ttl_seconds=settings.pubmed_cache_ttl_seconds,
    )
    crossref = (
        CrossrefAdapter(
            mailto=settings.crossref_mailto,
            timeout_seconds=settings.crossref_timeout_seconds,
            max_retries=settings.crossref_max_retries,
            cache=RedisQueryCache(settings.redis_url, label="Crossref DOI"),
            cache_ttl_seconds=settings.crossref_cache_ttl_seconds,
        ) if settings.crossref_mailto else None
    )
    result = await retrieve_pubmed(
        snapshot, adapter,
        selected_limit=settings.pubmed_selected_evidence_limit,
        max_per_document=settings.pubmed_max_passages_per_document,
        crossref=crossref,
        crossref_total_timeout_seconds=settings.crossref_total_timeout_seconds,
    )
    if persist:
        with SessionLocal() as session:
            persist_retrieval(session, result)
    print(f"CLAIM\n{snapshot.raw_text}\n")
    print("QUERY PLAN")
    for query in result.pack.query_plan.queries:
        print(f"{query.query_id} [{query.family}] {query.query}")
    print(f"\nPUBMED\n{len(result.pack.documents)} unique documents retrieved")
    print(f"Status: {result.diagnostics.status}\n")
    if result.diagnostics.missing_pmids:
        print(f"No normalized article for {len(result.diagnostics.missing_pmids)} PMIDs: "
              + ", ".join(result.diagnostics.missing_pmids))
    print("SELECTED DIRECT EVIDENCE (selection priority; not a verdict)")
    documents = {document.document_id: document for document in result.pack.documents}
    selected_ids = set(result.pack.selected_evidence_ids)
    by_evidence_id = {item.evidence_id: item for item in result.pack.passages}

    def print_evidence(ranked_id: str) -> None:
        ranked = by_evidence_id[ranked_id]
        document = documents[ranked.passage.document_id]
        directness = ranked.relationship_directness
        print(f"PMID: {document.pmid} | {ranked.evidence_id} | "
              f"selected: {'yes' if ranked_id in selected_ids else 'no'}")
        print(f"Title: {document.title}")
        print(f"Section: {ranked.passage.section} | retrieval_score: "
              f"{ranked.retrieval_score} | relationship_directness_score: "
              f"{directness.score} | relationship_direction: {directness.direction}")
        print(f"Incidental penalty: "
              f"{directness.factors.get('incidental_mention_penalty', 0)} | "
              f"exclusion penalty: "
              f"{directness.factors.get('exposure_excluded_penalty', 0)} | "
              f"quality_prior: {document.quality_prior} | "
              f"integrity_status: {document.integrity.status}")
        print(f"Selection priority: {ranked.selection_priority_score} | "
              f"selection factors: {ranked.selection_factors}")
        print(f"Direction reasons: {directness.reasons} | "
              f"warnings: {document.relationship_directness.warnings}\n")

    for evidence_id in result.pack.selected_evidence_ids:
        print_evidence(evidence_id)
    demoted: list[str] = []
    seen_documents: set[str] = set()
    for ranked in result.pack.passages:
        document = documents[ranked.passage.document_id]
        if document.document_id in seen_documents:
            continue
        seen_documents.add(document.document_id)
        detail = document.relationship_directness
        if (detail.direction in {"reverse", "incidental"}
                or detail.factors.get("exposure_only_background")
                or detail.factors.get("outcome_only_background")
                or detail.factors.get("exposure_excluded_population")):
            if not any(item.passage.document_id == document.document_id
                       and item.evidence_id in selected_ids for item in result.pack.passages):
                demoted.append(ranked.evidence_id)
    if demoted:
        print("HIGH TOPICAL HITS DEMOTED BY DIRECTNESS")
        for evidence_id in demoted[:5]:
            print_evidence(evidence_id)
    selected_pmids = [documents[item.passage.document_id].pmid
                      for item in result.pack.passages if item.evidence_id in selected_ids]
    print(f"Repeated selected PMIDs: {len(selected_pmids) != len(set(selected_pmids))}")
    print(f"Auditable passages: {len(result.pack.passages)}")
    print(f"Integrity status counts: {result.diagnostics.integrity_status_counts}")
    print(f"Crossref status counts: {result.diagnostics.crossref_status_counts}")
    print(f"DOI coverage: {result.diagnostics.doi_coverage}/{len(result.pack.documents)}")
    print(f"Partial metadata reason counts: {result.diagnostics.reason_counts}")
    print(f"Selected evidence IDs: {result.pack.selected_evidence_ids}")
    print(f"EVIDENCE PACK\nsha256: {result.pack.snapshot_hash}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve PubMed evidence for a stored claim")
    parser.add_argument("source", help="Stored claim UUID or raw claim text")
    parser.add_argument("--exposure")
    parser.add_argument("--outcome")
    parser.add_argument("--claim-type", choices=[kind.value for kind in ClaimType])
    args = parser.parse_args()
    asyncio.run(smoke(
        args.source, exposure=args.exposure, outcome=args.outcome,
        claim_type=ClaimType(args.claim_type) if args.claim_type else None,
    ))


if __name__ == "__main__":
    main()
