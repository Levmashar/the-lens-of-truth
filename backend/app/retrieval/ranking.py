"""Transparent lexical relevance ranking; scores are not medical confidence."""

import re

from app.retrieval.models import ClaimSnapshot, EvidencePassage, PubMedDocument, RankedPassage

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_RELATION_WORDS: dict[str, frozenset[str]] = {
    "causal": frozenset({"causal", "cause", "causes", "incidence", "risk"}),
    "association": frozenset({"association", "associated", "risk", "cohort"}),
    "prevention": frozenset({"prevention", "prevent", "prevents", "preventive"}),
    "treatment": frozenset({"treatment", "therapy", "therapeutic"}),
    "diagnostic": frozenset({"diagnosis", "diagnostic", "sensitivity"}),
    "safety": frozenset({"safety", "adverse", "harm"}),
}
_STOP = frozenset({"a", "and", "frequent", "higher", "in", "of", "the", "use", "users"})


def _words(value: str | None) -> set[str]:
    return {word.casefold() for word in _WORD.findall(value or "")
            if len(word) > 1 and word.casefold() not in _STOP}


def _coverage(needle: str | None, haystack: set[str]) -> float:
    words = _words(needle)
    return len(words & haystack) / len(words) if words else 0.0


def rank_passages(
    claim: ClaimSnapshot, documents: tuple[PubMedDocument, ...],
    passages: tuple[EvidencePassage, ...], *, limit: int = 12,
) -> tuple[RankedPassage, ...]:
    """Stable relevance only; publication type is not a study-quality judgment."""

    by_id = {document.document_id: document for document in documents}
    maximum_diversity = max((len(document.query_ids) for document in documents), default=1)
    ranked: list[tuple[float, str, EvidencePassage, dict[str, float]]] = []
    for passage in passages:
        document = by_id[passage.document_id]
        words = _words(passage.text)
        exposure = claim.pico.intervention_or_exposure if claim.pico else None
        outcome = claim.pico.outcome if claim.pico else None
        exposure_match = _coverage(exposure, words)
        outcome_match = _coverage(outcome, words)
        mesh_words = {
            word.casefold() for term in document.mesh_terms for word in _WORD.findall(term)
        }
        mesh_exposure = _coverage(exposure, mesh_words)
        mesh_outcome = _coverage(outcome, mesh_words)
        mesh_overlap = (mesh_exposure + mesh_outcome) / 2
        relation = _RELATION_WORDS.get(claim.claim_type or "", frozenset())
        relation_match = 1.0 if words & relation else 0.0
        diversity = len(document.query_ids) / maximum_diversity
        score = round(
            0.32 * exposure_match + 0.32 * outcome_match + 0.16 * mesh_overlap
            + 0.12 * relation_match + 0.08 * diversity, 4
        )
        factors = {
            "exposure_match": round(exposure_match, 4),
            "outcome_match": round(outcome_match, 4),
            "mesh_overlap": round(mesh_overlap, 4),
            "relation_match": relation_match,
            "query_diversity": round(diversity, 4),
        }
        ranked.append((score, passage.passage_id, passage, factors))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return tuple(
        RankedPassage(
            evidence_id=f"E{position}", passage=passage, rank=position,
            retrieval_score=score, factors=factors,
        )
        for position, (score, _, passage, factors) in enumerate(ranked[:limit], start=1)
    )
