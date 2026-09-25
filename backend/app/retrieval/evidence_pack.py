"""Canonical, immutable-by-contract Evidence Pack construction and deduplication."""

import hashlib
import json
from datetime import UTC, datetime

from app.retrieval.directness import annotate_directness
from app.retrieval.models import (
    ClaimSnapshot,
    EvidencePack,
    PubMedDocument,
    QueryPlan,
    RankedPassage,
)
from app.retrieval.ranking import select_top_evidence


def deduplicate_documents(
    documents: tuple[PubMedDocument, ...],
) -> tuple[PubMedDocument, ...]:
    """Use PMID first; DOI/title are fallbacks only for records without an ID."""

    merged: dict[str, PubMedDocument] = {}
    keys: dict[str, str] = {}
    for document in documents:
        aliases = [f"pmid:{document.pmid}"] if document.pmid else []
        if not aliases and document.doi:
            aliases.append(f"doi:{document.doi.casefold()}")
        if not aliases:
            aliases.append(f"title:{' '.join(document.title.casefold().split())}")
        target = next((keys[alias] for alias in aliases if alias in keys), document.document_id)
        existing = merged.get(target)
        if existing is None:
            merged[target] = document
        else:
            chosen = document if existing.abstract is None and document.abstract else existing
            query_ids = tuple(sorted(set(existing.query_ids) | set(document.query_ids)))
            merged[target] = chosen.model_copy(update={
                "document_id": target, "query_ids": query_ids,
            })
        for alias in aliases:
            keys[alias] = target
    return tuple(sorted(merged.values(), key=lambda document: document.document_id))


def canonical_pack_bytes(
    claim: ClaimSnapshot, plan: QueryPlan, documents: tuple[PubMedDocument, ...],
    passages: tuple[RankedPassage, ...], selected_evidence_ids: tuple[str, ...],
) -> bytes:
    """Hash only semantic snapshot fields, excluding retrieval wall-clock timestamps."""

    document_data = []
    for document in documents:
        data = document.model_dump(mode="json", exclude={"retrieved_at"})
        integrity = data["integrity"]
        integrity.pop("checked_at", None)
        for check in integrity["checks"]:
            check.pop("checked_at", None)
        if data["crossref"] is not None:
            data["crossref"]["check"].pop("checked_at", None)
        document_data.append(data)
    payload = {
        "evidence_pack_version": "1.3",
        "claim_snapshot": claim.model_dump(mode="json"),
        "query_plan": plan.model_dump(mode="json"),
        "documents": document_data,
        "passages": [passage.model_dump(mode="json") for passage in passages],
        "selected_evidence_ids": selected_evidence_ids,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def build_evidence_pack(
    claim: ClaimSnapshot, plan: QueryPlan, documents: tuple[PubMedDocument, ...],
    passages: tuple[RankedPassage, ...], *, retrieved_at: datetime | None = None,
    selected_limit: int = 8, max_per_document: int = 1,
) -> EvidencePack:
    """Freeze all passages and a separate diversified selection in one snapshot."""

    ordered_documents = tuple(sorted(documents, key=lambda document: document.document_id))
    ordered_documents, passages = annotate_directness(claim, ordered_documents, passages)
    audited_passages, selected_ids = select_top_evidence(
        passages, limit=selected_limit, max_per_document=max_per_document,
        documents=ordered_documents,
    )
    digest = hashlib.sha256(canonical_pack_bytes(
        claim, plan, ordered_documents, audited_passages, selected_ids,
    )).hexdigest()
    return EvidencePack(
        claim_id=claim.claim_id, claim_snapshot=claim, query_plan=plan,
        documents=ordered_documents, passages=audited_passages,
        selected_evidence_ids=selected_ids,
        retrieved_at=retrieved_at or datetime.now(UTC), snapshot_hash=digest,
    )
