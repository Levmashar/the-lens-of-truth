"""Transparent topical ranking and document-diverse evidence selection."""

import re
from collections import defaultdict

from app.retrieval.models import ClaimSnapshot, EvidencePassage, PubMedDocument, RankedPassage
from app.retrieval.study_quality import explicit_animal_subject

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_RELATION_WORDS: dict[str, frozenset[str]] = {
    "causal": frozenset({"causal", "cause", "causes", "incidence", "risk"}),
    "association": frozenset({"association", "associated", "risk", "cohort"}),
    "prevention": frozenset({"prevention", "prevent", "prevents", "preventive"}),
    "treatment": frozenset({"treatment", "therapy", "therapeutic"}),
    "diagnostic": frozenset({"diagnosis", "diagnostic", "sensitivity"}),
    "safety": frozenset({"safety", "adverse", "harm"}),
}
_STOP = frozenset({
    "a", "and", "body", "consumption", "frequent", "higher", "in", "of",
    "regular", "the", "usage", "use", "users",
})


def _words(value: str | None) -> set[str]:
    return {word.casefold() for word in _WORD.findall(value or "")
            if len(word) > 1 and word.casefold() not in _STOP}


def _coverage(needle: str | None, haystack: set[str]) -> float:
    words = _words(needle)
    return len(words & haystack) / len(words) if words else 0.0


def _concept_coverage(
    value: str | None, aliases: tuple[str, ...], haystack: set[str],
) -> float:
    # PICO wording remains available; linked labels only broaden lexical recall.
    return max((_coverage(term, haystack) for term in (value, *aliases)), default=0.0)


def _aliases(claim: ClaimSnapshot, role: str) -> tuple[str, ...]:
    slot = getattr(claim.pico, role) if claim.pico else None
    if slot is None:
        return ()
    head = re.split(r"\b(?:in|among)\b", slot, maxsplit=1, flags=re.I)[0]
    return tuple(
        label for entity in claim.entities
        if entity.entity_type == role and entity.mesh_id and not entity.ambiguous
        and _words(entity.surface_text)
        and re.search(rf"(?<!\w){re.escape(entity.surface_text)}(?!\w)", head, flags=re.I)
        for label in (entity.surface_text, entity.preferred_name)
        if label
    )


def rank_passages(
    claim: ClaimSnapshot, documents: tuple[PubMedDocument, ...],
    passages: tuple[EvidencePassage, ...],
) -> tuple[RankedPassage, ...]:
    """Rank *all* source passages; retrieval score is never evidence quality."""

    by_id = {document.document_id: document for document in documents}
    has_abstract = {
        passage.document_id for passage in passages if passage.section.upper() != "TITLE"
    }
    maximum_diversity = max(1, max((len(document.query_ids) for document in documents),
                                   default=0))
    exposure = claim.pico.intervention_or_exposure if claim.pico else None
    outcome = claim.pico.outcome if claim.pico else None
    exposure_aliases = _aliases(claim, "intervention_or_exposure")
    outcome_aliases = _aliases(claim, "outcome")
    ranked: list[tuple[float, str, EvidencePassage, dict[str, float]]] = []
    for passage in passages:
        document = by_id[passage.document_id]
        words = _words(passage.text)
        exposure_match = _concept_coverage(exposure, exposure_aliases, words)
        outcome_match = _concept_coverage(outcome, outcome_aliases, words)
        mesh_words = _words(" ".join(document.mesh_terms))
        mesh_exposure = _concept_coverage(exposure, exposure_aliases, mesh_words)
        mesh_outcome = _concept_coverage(outcome, outcome_aliases, mesh_words)
        mesh_overlap = (mesh_exposure + mesh_outcome) / 2
        relation = _RELATION_WORDS.get(claim.claim_type or "", frozenset())
        relation_match = float(bool(words & relation))
        diversity = len(document.query_ids) / maximum_diversity
        both = float(bool(exposure_match and outcome_match))
        exposure_present = float(bool(exposure_match))
        outcome_present = float(bool(outcome_match))
        mesh_both = float(bool(mesh_exposure and mesh_outcome))
        title_words = _words(document.title)
        generic_title = bool(
            outcome and exposure and
            _concept_coverage(outcome, outcome_aliases, title_words) and
            not _concept_coverage(exposure, exposure_aliases, title_words)
        )
        generic_penalty = 0.20 if outcome_present and not exposure_present else 0.0
        if generic_title:
            # A broad outcome-only title is weaker document-level focus even
            # when its long abstract mentions the exposure incidentally.
            generic_penalty += 0.08 if exposure_present else 0.05
        passage_type_bonus = 0.06 if passage.section.upper() != "TITLE" else 0.0
        title_penalty = 0.04 if (
            passage.section.upper() == "TITLE" and passage.document_id in has_abstract
        ) else 0.0
        score = round(max(0.0, min(1.0,
            0.28 * exposure_match + 0.28 * outcome_match + 0.12 * mesh_overlap
            + 0.08 * relation_match + 0.04 * diversity + 0.12 * both
            + passage_type_bonus - title_penalty - generic_penalty,
        )), 4)
        factors = {
            "exposure_match": round(exposure_match, 4),
            "outcome_match": round(outcome_match, 4),
            "exposure_present": exposure_present,
            "outcome_present": outcome_present,
            "both_core_concepts_present": both,
            "mesh_overlap": round(mesh_overlap, 4),
            "mesh_both_core_concepts": mesh_both,
            "relation_match": relation_match,
            "query_diversity": round(diversity, 4),
            "passage_type_bonus": passage_type_bonus,
            "title_penalty": title_penalty,
            "generic_background_penalty": round(generic_penalty, 4),
            "document_diversity_selection": 0.0,
        }
        ranked.append((score, passage.passage_id, passage, factors))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return tuple(
        RankedPassage(
            evidence_id=f"E{position}", passage=passage, rank=position,
            retrieval_score=score, factors=factors,
            passage_type="title" if passage.section.upper() == "TITLE" else "abstract",
        )
        for position, (score, _, passage, factors) in enumerate(ranked, start=1)
    )


def _representative(passages: list[RankedPassage]) -> RankedPassage:
    # The best claim-specific abstract section can differ from the passage with
    # the most lexical overlap (often a background paragraph).
    best = min(passages, key=lambda item: (
        -item.selection_priority_score,
        item.passage_type != "abstract",
        item.passage.passage_id,
    ))
    if best.passage_type == "title":
        direct_abstracts = [item for item in passages if (
            item.passage_type == "abstract"
            and item.relationship_directness.factors.get("exposure_in_passage") == 1.0
            and item.relationship_directness.factors.get("outcome_in_passage") == 1.0
            and item.selection_priority_score >= best.selection_priority_score - 0.08
        )]
        if direct_abstracts:
            return min(direct_abstracts, key=lambda item: (
                -item.selection_priority_score, item.passage.passage_id,
            ))
    return best


def _claim_focused(document: PubMedDocument) -> bool:
    detail = document.relationship_directness
    factors = detail.factors
    if "exposure_in_title" not in factors or "outcome_in_title" not in factors:
        # No source-grounded two-concept focus assessment was possible. Leave
        # existing eligibility untouched; do not infer irrelevance from it.
        return True
    exposure_title = factors.get("exposure_in_title", 0) == 1.0
    outcome_title = factors.get("outcome_in_title", 0) == 1.0
    same_section = factors.get("both_in_same_abstract_section", 0) == 1.0
    return (
        (exposure_title and outcome_title)
        or (same_section and exposure_title)
        or (same_section and outcome_title and detail.score >= 0.6)
        or (same_section and detail.score >= 0.75)
        or (document.endpoint_directness.score >= 0.35
            and factors.get("exposure_in_document") == 1.0
            and factors.get("outcome_in_document") == 1.0)
    )


def select_top_evidence(
    passages: tuple[RankedPassage, ...], *, limit: int = 8,
    max_per_document: int = 1, documents: tuple[PubMedDocument, ...] = (),
    claim: ClaimSnapshot | None = None,
) -> tuple[tuple[RankedPassage, ...], tuple[str, ...]]:
    """Annotate the full audit set and return ordered, document-diverse E IDs."""

    if limit < 1 or max_per_document < 1:
        raise ValueError("Selection limit and per-document maximum must be positive")
    documents_by_id = {document.document_id: document for document in documents}
    scored: list[RankedPassage] = []
    for passage in passages:
        document = documents_by_id.get(passage.passage.document_id)
        doc_directness = document.relationship_directness.score if document else 0.0
        doc_endpoint = document.endpoint_directness.score if document else 0.0
        passage_endpoint = passage.endpoint_directness.score
        quality = document.quality_prior if document else 0.4
        population_mismatch = bool(document and any(
            warning.endswith("_only_vs_male_claim") or warning.endswith("_only_vs_female_claim")
            for warning in document.applicability_warnings
        ))
        applicability_penalty = (0.22 if population_mismatch else
                                 0.06 if document and document.applicability_warnings else 0.0)
        endpoint_indirect_penalty = 0.16 if (
            document and document.endpoint_directness.factors.get("quantitative_outcome") == 1.0
            and doc_endpoint < 0.35
        ) else 0.0
        endpoint_title_focus_bonus = 0.16 if (
            document and not population_mismatch
            and document.relationship_directness.direction not in {"reverse", "incidental"}
            and document.endpoint_directness.factors.get("endpoint_in_title") == 1.0
            and document.relationship_directness.factors.get("exposure_in_document") == 1.0
        ) else 0.0
        relationship_mismatch_penalty = 0.22 if (
            document and document.relationship_directness.direction in {"reverse", "incidental"}
        ) else 0.0
        factors = {
            "retrieval_component": round(0.22 * passage.retrieval_score, 4),
            "passage_directness_component": round(
                0.28 * passage.relationship_directness.score, 4
            ),
            "document_directness_component": round(0.12 * doc_directness, 4),
            "passage_endpoint_component": round(0.22 * passage_endpoint, 4),
            "document_endpoint_component": round(0.11 * doc_endpoint, 4),
            "endpoint_title_focus_bonus": endpoint_title_focus_bonus,
            "quality_prior_component": round(0.05 * quality, 4),
            "applicability_penalty": applicability_penalty,
            "endpoint_indirect_penalty": endpoint_indirect_penalty,
            "relationship_mismatch_penalty": relationship_mismatch_penalty,
            "priority_normalizer": 1.16,
        }
        priority = round(max(0.0, min(1.0,
            (sum(value for key, value in factors.items()
                 if key.endswith("_component") or key.endswith("_bonus"))
             - applicability_penalty - endpoint_indirect_penalty
             - relationship_mismatch_penalty) / factors["priority_normalizer"],
        )), 4)
        scored.append(passage.model_copy(update={
            "selection_priority_score": priority, "selection_factors": factors,
        }))
    by_document: dict[str, list[RankedPassage]] = defaultdict(list)
    for passage in scored:
        by_document[passage.passage.document_id].append(passage)
    representatives: list[RankedPassage] = []
    for document_passages in by_document.values():
        representative = _representative(document_passages)
        representatives.append(representative)
        if max_per_document > 1:
            representatives.extend(
                passage for passage in document_passages
                if passage.evidence_id != representative.evidence_id
            )
    representatives.sort(key=lambda item: (
        -item.selection_priority_score, item.passage.passage_id,
    ))
    retracted = {document.document_id for document in documents
                 if document.integrity.status == "retracted"}
    claim_targets_animals = bool(claim and explicit_animal_subject(
        " ".join((claim.raw_text, claim.pico.intervention_or_exposure or ""
                  if claim.pico else "")),
    ))
    nonhuman = {
        document.document_id for document in documents
        if document.study_design in {"animal_study", "in_vitro"} and not claim_targets_animals
    }
    unfocused = {
        document.document_id for document in documents if not _claim_focused(document)
    }
    direct_quantitative = {
        document.document_id for document in documents
        if document.endpoint_directness.factors.get("quantitative_outcome") == 1.0
        and document.endpoint_directness.score >= 0.5
    }
    weak_endpoint = {
        document.document_id for document in documents
        if len(direct_quantitative) >= 3
        and document.endpoint_directness.factors.get("quantitative_outcome") == 1.0
        and document.endpoint_directness.score < 0.35
    }
    counts: dict[str, int] = defaultdict(int)
    selected: list[RankedPassage] = []
    for passage in representatives:
        document_id = passage.passage.document_id
        if (document_id in retracted or document_id in nonhuman
                or document_id in unfocused or document_id in weak_endpoint):
            continue
        if counts[document_id] >= max_per_document:
            continue
        selected.append(passage)
        counts[document_id] += 1
        if len(selected) == limit:
            break
    selected_ids = tuple(item.evidence_id for item in selected)
    selected_set = set(selected_ids)
    annotated = []
    for passage in scored:
        is_selected = passage.evidence_id in selected_set
        reason = None
        if is_selected:
            if passage.passage_type == "abstract":
                reason = ("relevant_abstract" if passage.factors["both_core_concepts_present"]
                          or passage.factors["mesh_both_core_concepts"]
                          else "background_fallback")
            elif len(by_document[passage.passage.document_id]) == 1:
                reason = "title_only"
            else:
                reason = "title_unique_relevance"
        elif passage.passage.document_id in retracted:
            reason = "retracted_excluded"
        elif passage.passage.document_id in nonhuman:
            reason = "nonhuman_evidence_excluded"
        elif passage.passage.document_id in unfocused:
            reason = "insufficient_claim_focus"
        elif passage.passage.document_id in weak_endpoint:
            reason = "endpoint_indirect_when_direct_alternatives_exist"
        annotated.append(passage.model_copy(update={
            "selected_for_judging": is_selected, "selection_reason": reason,
            "factors": {**passage.factors, "document_diversity_selection": float(is_selected)},
        }))
    return tuple(annotated), selected_ids
