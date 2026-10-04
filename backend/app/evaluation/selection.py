"""Evaluation-only subsets. Never fetch, delete Pack evidence or force directions."""

import hashlib
from typing import Literal

from app.retrieval.evidence_pack import canonical_pack_bytes
from app.retrieval.models import EvidencePack
from app.retrieval.sufficiency import design_fact


def subset_pack(pack: EvidencePack, selected_ids: tuple[str, ...], *,
                allow_incompatible_context: bool = False) -> EvidencePack:
    if not selected_ids or len(set(selected_ids)) != len(selected_ids):
        raise ValueError("Selection must be nonempty and unique")
    passages = {p.evidence_id: p for p in pack.passages}
    if not set(selected_ids) <= set(passages):
        raise ValueError("Unknown selected reference")
    docs = {d.document_id: d for d in pack.documents}
    if any(docs[passages[i].passage.document_id].integrity.status == "retracted" or
           (not allow_incompatible_context and
            docs[passages[i].passage.document_id].evidence_role_hint == "incompatible")
           for i in selected_ids):
        raise ValueError("Cannot select retracted/incompatible evidence")
    new_passages = tuple(p.model_copy(update={"selected_for_judging":
                                            p.evidence_id in selected_ids}) for p in pack.passages)
    digest = hashlib.sha256(canonical_pack_bytes(
        pack.claim_snapshot, pack.query_plan, pack.documents, new_passages,
        selected_ids, pack_version=pack.evidence_pack_version,
    )).hexdigest()
    return pack.model_copy(update={"passages": new_passages, "selected_evidence_ids": selected_ids,
                                   "snapshot_hash": digest})


def lean_selection(pack: EvidencePack) -> EvidencePack:
    """Design/role/relevance only, no direction or expected-label features."""
    docs = {d.document_id: d for d in pack.documents}
    selected = [p for p in pack.passages if p.evidence_id in pack.selected_evidence_ids]
    ordered = sorted(selected, key=lambda p: (
        design_fact(docs[p.passage.document_id]).analysis_design in
        {"randomized_intervention", "systematic_review", "meta_analysis"},
        bool(docs[p.passage.document_id].authoritative and
             getattr(docs[p.passage.document_id].authoritative, "document_purpose", None) in
             {"causal_assessment", "systematic_evidence_summary"}),
        p.endpoint_directness.score, p.selection_priority_score,
    ), reverse=True)
    chosen: list[str] = []
    seen: set[str] = set()
    counts: dict[str, int] = {"research": 0, "assessment": 0, "context": 0}
    for passage in ordered:
        doc = docs[passage.passage.document_id]
        if doc.document_id in seen:
            continue
        kind: Literal["research", "assessment", "context"] = (
            "context" if doc.evidence_role_hint == "contextual" else
            "assessment" if doc.authoritative else "research")
        quota = {"research": 3, "assessment": 1, "context": 1}[kind]
        if counts[kind] >= quota:
            continue
        counts[kind] += 1
        chosen.append(passage.evidence_id)
        seen.add(doc.document_id)
    return subset_pack(pack, tuple(chosen))


def oracle_selection(pack: EvidencePack, document_ids: tuple[str, ...]) -> EvidencePack:
    """Manually reviewed source selection lives in runtime, not a medical lookup."""
    docs = {d.document_id for d in pack.documents}
    if not document_ids or not set(document_ids) <= docs:
        raise ValueError("Oracle requires actual frozen documents")
    selected = []
    for identifier in document_ids:
        available = [p for p in pack.passages if p.passage.document_id == identifier]
        if not available:
            raise ValueError("Oracle source has no frozen passage")
        fallback = next((p for p in available if p.passage_type != "title"), available[0])
        representative = next((p for p in available
                               if p.evidence_id in pack.selected_evidence_ids), fallback)
        selected.append(representative.evidence_id)
    # Oracle review may deliberately show incompatible evidence as a negative
    # scope/context control. Its role is NOT upgraded, integrity is NOT bypassed,
    # and this function is never called by the application pipeline.
    return subset_pack(pack, tuple(selected), allow_incompatible_context=True)
