"""Version 1.5: bounded contextual inclusion, never a support-direction vote."""

from collections import defaultdict

from app.retrieval.models import PubMedDocument, RankedPassage

HARD_EXCLUSIONS = frozenset({
    "retracted_excluded", "nonhuman_evidence_excluded", "non_evidence_publication_excluded",
    "nonclinical_visual_context_excluded", "exposure_arm_population_mismatch_excluded",
})
CONTEXTUAL_EXCLUSIONS = frozenset({
    "unstated_active_comparator_excluded", "specific_outcome_endpoint_absent_excluded",
    "post_disease_endpoint_excluded", "indirect_relationship_question_excluded",
    "endpoint_indirect_when_direct_alternatives_exist", "direct_title_evidence_available",
})


def select_role_aware(documents: tuple[PubMedDocument, ...], passages: tuple[RankedPassage, ...],
                      previous_ids: tuple[str, ...], *, limit: int
                      ) -> tuple[tuple[PubMedDocument, ...], tuple[RankedPassage, ...],
                                 tuple[str, ...]]:
    by_doc: dict[str, list[RankedPassage]] = defaultdict(list)
    for item in passages:
        by_doc[item.passage.document_id].append(item)
    direct: list[RankedPassage] = []
    context: list[RankedPassage] = []
    annotated_docs = []
    for doc in documents:
        items = sorted(by_doc[doc.document_id], key=lambda p: (
            p.passage.section == "TITLE", -p.selection_priority_score, p.rank,
        ))
        representative = next((p for p in items if p.evidence_id in previous_ids), items[0])
        reasons = {p.selection_reason for p in items}
        role = "incompatible"
        if doc.integrity.status != "retracted" and not reasons & HARD_EXCLUSIONS:
            if (doc.authoritative and doc.authoritative.currency == "current"
                    and doc.relationship_directness.direction == "aligned"
                    and doc.relationship_directness.factors.get("both_in_same_abstract_section")
                    and doc.endpoint_directness.score >= 0.35
                    and "specific_size_endpoint_absent" not in doc.endpoint_directness.warnings):
                role = "direct"
            elif representative.evidence_id in previous_ids:
                role = "direct"
            elif reasons & CONTEXTUAL_EXCLUSIONS:
                role = "contextual"
            # Approved guidance often names the broader endpoint (skin cancer)
            # rather than an invasive subtype. It can enter only as context.
            elif doc.authoritative and doc.relationship_directness.factors.get(
                "exposure_in_document", 0,
            ) and any(p.retrieval_score >= 0.25 for p in items):
                role = "contextual"
        if role == "direct":
            # Reverse question / weak background must not be promoted by a quota.
            if (doc.relationship_directness.direction in {"incidental", "reverse"}
                    or doc.endpoint_directness.score < 0.35):
                role = "contextual"
        if role == "direct":
            direct.append(representative)
        elif role == "contextual":
            context.append(representative)
        annotated_docs.append(doc.model_copy(update={"evidence_role_hint": role}))
    # Interleave kinds: reserve at most two direct summaries when present, and
    # preserve research slots. Within a kind use existing relevance only.
    docs = {d.document_id: d for d in annotated_docs}
    direct.sort(key=lambda p: (-p.selection_priority_score, p.rank))
    summaries = [p for p in direct if docs[p.passage.document_id].authoritative]
    research = [p for p in direct if not docs[p.passage.document_id].authoritative]
    ordered = summaries[:min(2, max(1, limit // 3))] + research
    ordered += [p for p in direct if p not in ordered]
    selected = ordered[:limit]
    context.sort(key=lambda p: (-p.selection_priority_score, p.rank))
    # Context consumes free slots only; max two documents, never decisive.
    selected += context[:min(2, max(0, limit - len(selected)))]
    ids = tuple(p.evidence_id for p in selected)
    audited_items = tuple(p.model_copy(update={
        "selected_for_judging": p.evidence_id in ids,
        "selection_reason": ("contextual_relevance" if p.evidence_id in ids
                             and docs[p.passage.document_id].evidence_role_hint == "contextual"
                             else "direct_assessment_relevance" if p.evidence_id in ids
                             and docs[p.passage.document_id].authoritative
                             else p.selection_reason),
        "selection_factors": {**p.selection_factors,
                              **({f"prior_reason:{p.selection_reason}": 1.0}
                                 if p.selection_reason else {})},
        "factors": {**p.factors, "document_diversity_selection": float(p.evidence_id in ids)},
    }) for p in passages)
    return tuple(annotated_docs), audited_items, ids
