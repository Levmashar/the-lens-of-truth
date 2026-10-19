"""Retrieval V2 search vocabulary and conservative, auditable scope ceilings.

Search synonyms never rewrite PICO. Missing qualifiers may only reduce relevance.
"""

import re
from typing import Literal

from app.retrieval.models import (
    ClaimSnapshot,
    PubMedDocument,
    QueryPlan,
    RankedPassage,
    RetrievalContext,
    RetrievalQuery,
)
from app.retrieval.query_planner import plan_pubmed_queries

_GRAMMAR = frozenset(
    "a an the and or of for to from in on with by at as is are be "
    "using use usage uses your my our their his her its while when "
    "makes make can may could does do not no than more less "
    "increases increase decreases decrease reduces reduce improves improve "
    "worsens worsen causes cause risk levels level "
    "deterioration down".split()
)
# Search vocabulary, not exposure-outcome pairs or rules about verdicts.
_SYNONYMS = (
    ("phone", "smartphone", "mobile phone", "cell phone", "cellular phone"),
    ("screen", "digital device", "electronic device", "screen time"),
    ("lying", "laying", "recumbent", "supine"),
    ("side", "lateral", "side lying", "lateral decubitus"),
    ("myopia", "short sightedness", "short-sightedness", "nearsightedness"),
    ("eyesight", "vision", "visual acuity"),
    ("exercise", "physical activity"),
    ("sleep", "sleeping"),
    ("cold", "common cold"),
    ("progression", "deterioration", "worsening"),
    ("developing", "development", "incidence", "incident", "onset"),
    ("daily", "every day"),
)


def words(text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            w.casefold()
            for w in re.findall(r"[\w]+", text)
            if (len(w) > 1 or w.isdigit()) and w.casefold() not in _GRAMMAR
        )
    )


def variants(term: str) -> tuple[str, ...]:
    result = [term]
    for group in _SYNONYMS:
        if term.casefold() in group:
            result.extend(group)
    return tuple(dict.fromkeys(result))[:6]


def concepts(claim: ClaimSnapshot, role: str, *, core: bool = False) -> tuple[str, ...]:
    literal = getattr(claim.pico, role) if claim.pico else None
    if not literal:
        return ()
    head = (
        re.split(r"\b(?:while|when|during|in|among|with|under)\b", literal, maxsplit=1, flags=re.I)[
            0
        ]
        if core
        else literal
    )
    entities = tuple(
        e
        for e in claim.entities
        if e.entity_type == role
        and e.mesh_id
        and not e.ambiguous
        and (e.confidence or 0) >= 0.9
        and re.search(r"(?<!\w)" + re.escape(e.surface_text) + r"(?!\w)", head, re.I)
    )
    if core and entities:
        values = (t for e in entities for t in (e.surface_text, e.preferred_name) if t)
        return tuple(dict.fromkeys(t.casefold() for t in values))[:4]
    if core:
        literal = re.split(
            r"\b(?:while|when|during|in|among|with|under)\b", literal, maxsplit=1, flags=re.I
        )[0]
    if entities:
        # Medical concepts are atoms, including lettered vitamins and multiword
        # diagnoses. Remaining literal qualifiers are required independently.
        remainder = literal
        for entity in entities:
            remainder = re.sub(
                r"(?<!\w)" + re.escape(entity.surface_text) + r"(?!\w)", " ", remainder, flags=re.I
            )
        return tuple(
            dict.fromkeys((*(e.surface_text.casefold() for e in entities), *words(remainder)))
        )
    return words(literal)


def linked_variants(claim: ClaimSnapshot, term: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                term,
                *(
                    e.preferred_name
                    for e in claim.entities
                    if e.surface_text.casefold() == term.casefold()
                    and e.mesh_id
                    and not e.ambiguous
                    and (e.confidence or 0) >= 0.9
                    and e.preferred_name
                ),
            )
        )
    )


def _group(terms: tuple[str, ...], *, field: bool = True) -> str:
    suffix = "[Title/Abstract]" if field else ""
    return "(" + " OR ".join(f'"{v}"{suffix}' for t in terms for v in variants(t)) + ")"


def plan_adaptive_queries(claim: ClaimSnapshot) -> QueryPlan:
    left = concepts(claim, "intervention_or_exposure")
    right = concepts(claim, "outcome", core=True)
    if not left or not right:
        return plan_pubmed_queries(claim).model_copy(update={"version": "2.0"})
    full_left = " AND ".join(_group(linked_variants(claim, t)) for t in left)
    full_right = (
        _group(right)
        if len(right) == 1 or any(" " in t for t in right)
        else " AND ".join(_group((t,)) for t in right)
    )
    core = concepts(claim, "intervention_or_exposure", core=True)
    core_left = (
        _group(core) if any(" " in t for t in core) else " AND ".join(_group((t,)) for t in core)
    )
    # Linked two-concept MeSH search remains first when available.
    mesh = tuple(q for q in plan_pubmed_queries(claim).queries if q.family == "mesh")[:1]
    specs: list[tuple[str, str, tuple[str, ...]]] = [
        (q.family, q.query, q.source_fields) for q in mesh
    ]
    specs.append(
        (
            "expanded",
            f"({full_left}) AND ({full_right})",
            ("pico.intervention_or_exposure", "pico.outcome", "retrieval_search_synonyms"),
        )
    )
    if core_left and core_left != full_left:
        specs.append(
            (
                "broad_context",
                f"({core_left}) AND ({full_right})",
                ("pico.exposure_core", "pico.outcome", "qualifiers_removed_for_search_only"),
            )
        )
    # Specificity ladder always keeps both medical anchors, never outcome alone.
    anchor = specs[-1][1]
    endpoint = claim.pico.outcome if claim.pico else ""
    stage = (
        ("incidence", "prevention", "onset")
        if (
            claim.claim_type == "prevention"
            or re.search(r"\b(?:developing|development|incidence|onset)\b", endpoint or "", re.I)
        )
        else (
            ("progression", "severity", "worsening")
            if re.search(r"\b(?:progression|deterioration|worsen\w*)\b", endpoint or "", re.I)
            else ()
        )
    )
    if stage:
        specs.append(
            ("endpoint", f"({anchor}) AND ({_group(stage)})", ("pico.outcome.stage", "claim_type"))
        )
        anchor = specs[-1][1]
    specs.append(
        (
            "relation",
            f'({anchor}) AND ("Systematic Review"[Publication Type] OR '
            '"Meta-Analysis"[Publication Type] OR "Cohort Studies"[MeSH Terms])',
            ("question_design_recall",),
        )
    )
    seen = set()
    queries: list[RetrievalQuery] = []
    for family, query, fields in specs:
        if query not in seen:
            seen.add(query)
            queries.append(
                RetrievalQuery(
                    query_id=f"Q{len(queries) + 1}",
                    family=family,  # type: ignore[arg-type]
                    query=query,
                    source_fields=fields,
                    relation_semantics=claim.claim_type,
                )
            )
    return QueryPlan(version="2.0", claim_type=claim.claim_type, queries=tuple(queries[:5]))


def discovery_terms(claim: ClaimSnapshot, *, broad: bool) -> str:
    left = concepts(claim, "intervention_or_exposure", core=broad)
    right = concepts(claim, "outcome", core=True)
    return " ".join(dict.fromkeys((*left, *right)))[:220]


def scholarly_query(claim: ClaimSnapshot, *, broad: bool, provider: str) -> str:
    if provider == "openalex":
        return discovery_terms(claim, broad=broad)
    left = concepts(claim, "intervention_or_exposure", core=broad)
    right = concepts(claim, "outcome", core=True)
    if not left or not right:
        return ""
    return " AND ".join((*(_group((t,), field=False) for t in left), _group(right, field=False)))


def _present(term: str, text: str) -> bool:
    return any(
        re.search(r"(?<!\w)" + re.escape(v) + r"(?:s|es)?(?!\w)", text, re.I)
        for v in variants(term)
    )


def classify(claim: ClaimSnapshot, doc: PubMedDocument) -> RetrievalContext:
    text = doc.title + " " + (doc.abstract or "")
    left = concepts(claim, "intervention_or_exposure", core=True)
    right = concepts(claim, "outcome", core=True)
    exposure = bool(left) and any(_present(t, text) for t in left)
    outcome = bool(right) and any(_present(t, text) for t in right)
    required = concepts(claim, "intervention_or_exposure")
    missing = [
        f"exposure:{t}"
        for t in required
        if not any(_present(v, text) for v in linked_variants(claim, t))
    ]
    # Exact endpoint/stage and specified population are never inferred from a core hit.
    for role in ("outcome", "population", "comparator", "timeframe"):
        for term in concepts(claim, role):
            if not any(_present(v, text) for v in linked_variants(claim, term)):
                missing.append(f"{role}:{term}")
    classification: Literal["direct", "related_indirect", "background_guidance", "irrelevant"] = (
        "irrelevant"
        if not (exposure and outcome)
        else "background_guidance"
        if (
            doc.authoritative
            and (
                doc.metadata_provenance.get("purpose") != "reviewed_manifest"
                or doc.authoritative.currency != "current"
            )
        )
        else "related_indirect"
        if missing
        else "direct"
    )
    if (
        doc.authoritative
        and outcome
        and not exposure
        and doc.metadata_provenance.get("purpose") != "reviewed_manifest"
    ):
        classification = "background_guidance"
    if claim.pico and re.search(
        r"\b(?:progression|deterioration|worsen\w*)\b", claim.pico.outcome or "", re.I
    ):
        if not _present("progression", text):
            missing.append("outcome:progression")
            if classification == "direct":
                classification = "related_indirect"
    # A device used to detect a disease is not research about device exposure
    # changing disease risk. Keep these discovery leads out of clinical context.
    if (
        not doc.authoritative
        and claim.claim_type != "diagnostic"
        and re.search(
            r"\b(?:screening|detecting|detection|diagnostic|diagnosis|refractive screener|"
            r"photoscreening|photoscreener|"
            r"artificial intelligence|automated refraction)\b",
            doc.title,
            re.I,
        )
    ):
        classification = "irrelevant"
    return RetrievalContext(
        classification=classification,
        matched_fields=tuple(
            f for f, yes in [("exposure_core", exposure), ("outcome_core", outcome)] if yes
        ),
        missing_qualifiers=tuple(missing),
        discovery_providers=tuple(
            sorted(
                k.removeprefix("discovered_by:")
                for k in doc.metadata_provenance
                if k.startswith("discovered_by:")
            )
        ),
        identity_basis="approved_origin_content" if doc.authoritative else "ncbi_efetch_identity",
    )


def constrain_selection(
    claim: ClaimSnapshot,
    documents: tuple[PubMedDocument, ...],
    passages: tuple[RankedPassage, ...],
    previous: tuple[str, ...],
    *,
    limit: int,
) -> tuple[tuple[PubMedDocument, ...], tuple[RankedPassage, ...], tuple[str, ...]]:
    from app.retrieval.evidence_roles import CONTEXTUAL_EXCLUSIONS, HARD_EXCLUSIONS

    docs = []
    candidates = []
    direct_candidates = []
    for doc in documents:
        context = classify(claim, doc)
        items = [p for p in passages if p.passage.document_id == doc.document_id]
        role = doc.evidence_role_hint
        representatives = [p for p in items if p.evidence_id in previous]
        if not representatives and items:
            representatives = [max(items, key=lambda p: p.selection_priority_score)]
        # Title/sibling diversification exclusions are not medical scope gaps.
        # An already direct reviewed source keeps the existing semantic decision.
        scope_reasons = CONTEXTUAL_EXCLUSIONS - {"direct_title_evidence_available"}
        prior_reasons = (
            {
                r
                for p in representatives
                for r in scope_reasons
                if p.selection_reason == r or f"prior_reason:{r}" in p.selection_factors
            }
            if role != "direct"
            else set()
        )
        if context.classification == "irrelevant":
            role = "incompatible"
        elif context.classification != "direct":
            role = "contextual"
        elif prior_reasons:
            role = "contextual"
            context = context.model_copy(
                update={
                    "classification": "related_indirect",
                    "missing_qualifiers": (
                        *context.missing_qualifiers,
                        *(f"deterministic_guard:{r}" for r in sorted(prior_reasons)),
                    ),
                }
            )
        else:
            role = "direct"
        # Previous hard exclusions and retractions always win over broad recall.
        if (
            doc.integrity.status == "retracted"
            or any("preprint" in t.casefold() for t in doc.publication_types)
        ) or any(
            p.selection_reason in HARD_EXCLUSIONS
            or any(f"prior_reason:{r}" in p.selection_factors for r in HARD_EXCLUSIONS)
            for p in items
        ):
            role = "incompatible"
        docs.append(
            doc.model_copy(update={"retrieval_context": context, "evidence_role_hint": role})
        )
        if role == "direct":
            usable = [p for p in items if p.passage.section != "TITLE"]
            if usable:
                direct_candidates.append(max(usable, key=lambda p: p.selection_priority_score))
        if role == "contextual":
            abstracts = [p for p in items if p.passage.section != "TITLE"]
            if abstracts and doc.integrity.status in {"valid", "corrected", "updated"}:
                candidates.append(max(abstracts, key=lambda p: p.selection_priority_score))
    by_doc = {d.document_id: d for d in docs}
    direct_candidates.sort(key=lambda p: (-p.selection_priority_score, p.rank))
    # Preserve the existing summary/research balance and direct-selection order,
    # then fill with exact-match candidates the phrase matcher could not recognize.
    selected = [
        i
        for i in previous
        if any(
            p.evidence_id == i and by_doc[p.passage.document_id].evidence_role_hint == "direct"
            for p in passages
        )
    ]
    selected_docs = {p.passage.document_id for p in passages if p.evidence_id in selected}
    selected += [
        p.evidence_id for p in direct_candidates if p.passage.document_id not in selected_docs
    ]
    selected = selected[:limit]
    # Existing maximum two context documents remains unchanged.
    candidates.sort(
        key=lambda p: (
            -int(
                any(
                    _present(t, by_doc[p.passage.document_id].title)
                    for t in concepts(claim, "intervention_or_exposure", core=True)
                )
            ),
            -int(
                bool(
                    re.search(
                        r"\b(?:risk|association|progression|systematic|meta.analysis)\b",
                        by_doc[p.passage.document_id].title,
                        re.I,
                    )
                )
            ),
            -p.selection_priority_score,
            p.rank,
        )
    )
    selected += [p.evidence_id for p in candidates[: min(2, max(0, limit - len(selected)))]]
    ids = tuple(selected)
    audited = tuple(
        p.model_copy(
            update={
                "selected_for_judging": p.evidence_id in ids,
                "selection_reason": "contextual_relevance"
                if p.evidence_id in ids
                and by_doc[p.passage.document_id].evidence_role_hint == "contextual"
                else p.selection_reason,
            }
        )
        for p in passages
    )
    return tuple(docs), audited, ids
