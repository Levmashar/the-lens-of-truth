"""Live, explicit PubMed smoke check for an existing normalized claim.

Run for a stored claim UUID, or pass explicit source-grounded PICO fields.
"""

import argparse
import asyncio
from uuid import UUID, uuid4

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
    result = await retrieve_pubmed(snapshot, adapter)
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
        print(f"Missing metadata for {len(result.diagnostics.missing_pmids)} PMIDs: "
              + ", ".join(result.diagnostics.missing_pmids))
    print("TOP EVIDENCE")
    documents = {document.document_id: document for document in result.pack.documents}
    for ranked in result.pack.passages[:5]:
        document = documents[ranked.passage.document_id]
        print(f"{ranked.evidence_id} | PMID {document.pmid} | score {ranked.retrieval_score}")
        print(f"Title: {document.title}")
        print(f"{ranked.passage.section}: {ranked.passage.text[:350]}\n")
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
