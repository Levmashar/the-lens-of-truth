"""Bounded, reproducible PubMed query planning from source-grounded fields."""

import re

from app.medical.entities import MedicalEntity
from app.retrieval.lexical import lay_variants
from app.retrieval.models import ClaimSnapshot, QueryPlan, RetrievalQuery

_STOPWORDS = frozenset({
    "a", "an", "and", "associated", "causes", "cause", "frequent", "higher", "in",
    "increases", "is", "of", "risk", "the", "use", "users", "with", "developing",
    "regular", "usage", "consumption", "body", "increased", "decreased",
    "increase", "decrease", "rate", "rates", "level", "levels",
    "eat", "eats", "eating", "improve", "improves", "improved", "improving",
})
_NUMERIC = re.compile(r"(?<!\w)(?:\d+(?:\.\d+)?\s*%|\d{1,3}(?:,\d{3})+)(?!\w)")
_MEASURED_OUTCOME = re.compile(
    r"\b(?:levels?|concentrations?|serum|plasma|blood|mass|gain|growth|"
    r"severity|duration|pressure|glucose|cholesterol)\b", re.I,
)
_SAFE_TOKEN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_DIRECTIONAL_OUTCOME_PREFIX = re.compile(
    r"^\s*(?:lowers|reduces|decreases|increases|raises|boosts|improves|worsens)\s+"
    r"(?:the\s+)?", re.I,
)
_RELATION_TERMS: dict[str, tuple[str, ...]] = {
    "causal": ("risk", "incidence", "causation", "cohort"),
    "association": ("association", "risk", "cohort"),
    "prevention": ("prevention", "preventive", "trial"),
    "treatment": ("treatment", "therapy", "trial"),
    "diagnostic": ("diagnosis", "sensitivity", "specificity"),
    "safety": ("safety", "adverse", "harm"),
}


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token.casefold() for token in _SAFE_TOKEN.findall(value)
        if token.casefold() not in _STOPWORDS and len(token) > 1
    )[:6]


def _slot_entity(
    entities: tuple[MedicalEntity, ...], role: str, slot: str | None,
) -> MedicalEntity | None:
    if slot is None:
        return None
    # "in male body" describes the population, not the intervention in
    # "soy consumption in male body". A linker can find Male in that full
    # PICO phrase, but it must not become the exposure's MeSH query anchor.
    head = re.split(r"\b(?:in|among)\b", slot, maxsplit=1, flags=re.I)[0]
    return next((
        entity for entity in entities
        if entity.entity_type == role and _lexical_terms(entity.surface_text)
        and re.search(rf"(?<!\w){re.escape(entity.surface_text)}(?!\w)", head, flags=re.I)
    ), None)


def _lexical_terms(value: str) -> str:
    words = _tokens(value)
    return " AND ".join(f'"{word}"[Title/Abstract]' for word in words)


def _outcome_search_text(value: str) -> str:
    """Remove only a leading effect verb from retrieval wording, never PICO."""

    stripped = _DIRECTIONAL_OUTCOME_PREFIX.sub("", value, count=1).strip()
    return stripped if _tokens(stripped) else value


def plan_pubmed_queries(claim: ClaimSnapshot) -> QueryPlan:
    """Create a small set of queries without adding unstated clinical details."""

    pico = claim.pico
    exposure = pico.intervention_or_exposure if pico else None
    outcome = pico.outcome if pico else None
    exposure_entity = _slot_entity(claim.entities, "intervention_or_exposure", exposure)
    outcome_entity = _slot_entity(claim.entities, "outcome", outcome)
    # Use a source-grounded linked mention when it is the asserted concept;
    # otherwise fall back to the full PICO slot rather than a generic modifier.
    exposure_head = re.split(r"\b(?:in|among)\b", exposure or "", maxsplit=1, flags=re.I)[0]
    exposure_term = exposure_entity.surface_text if exposure_entity else exposure_head
    outcome_term = outcome_entity.surface_text if outcome_entity else outcome
    queries: list[RetrievalQuery] = []
    warnings: list[str] = []

    if exposure_entity and outcome_entity and all(
        entity.mesh_id and entity.match_type in {"exact", "synonym"}
        and not entity.ambiguous and entity.preferred_name
        and entity.confidence is not None and entity.confidence >= 0.9
        for entity in (exposure_entity, outcome_entity)
    ):
        queries.append(RetrievalQuery(
            query_id="Q1", family="mesh",
            query=(f'"{exposure_entity.preferred_name}"[MeSH Terms] AND '
                   f'"{outcome_entity.preferred_name}"[MeSH Terms]'),
            source_fields=("entities.intervention_or_exposure.mesh_id", "entities.outcome.mesh_id"),
            relation_semantics=claim.claim_type,
        ))

    if exposure_term and outcome_term:
        left = _lexical_terms(exposure_term)
        right = _lexical_terms(_outcome_search_text(outcome_term))
        if left and right:
            lexical = f"({left}) AND ({right})"
            lexical_sources = (
                "entities.intervention_or_exposure.surface_text" if exposure_entity
                else "pico.intervention_or_exposure",
                "entities.outcome.surface_text" if outcome_entity else "pico.outcome",
            )
            queries.append(RetrievalQuery(
                query_id=f"Q{len(queries) + 1}", family="lexical", query=lexical,
                source_fields=lexical_sources,
                relation_semantics=claim.claim_type,
            ))
            relation = _RELATION_TERMS.get(claim.claim_type or "")
            if relation:
                terms = " OR ".join(f'"{word}"[Title/Abstract]' for word in relation)
                queries.append(RetrievalQuery(
                    query_id=f"Q{len(queries) + 1}", family="relation",
                    query=f"{lexical} AND ({terms})",
                    source_fields=(*lexical_sources, "claim_type"),
                    relation_semantics=claim.claim_type,
                ))
            if outcome and _MEASURED_OUTCOME.search(outcome):
                precision = (
                    f"({left}) AND ({right}) AND "
                    '("levels"[Title/Abstract] OR "concentration"[Title/Abstract] OR '
                    '"serum"[Title/Abstract] OR "plasma"[Title/Abstract] OR '
                    '"change"[Title/Abstract] OR "measured"[Title/Abstract] OR '
                    '"growth"[Title/Abstract] OR "gain"[Title/Abstract] OR '
                    '"mass"[Title/Abstract])'
                )
                queries.append(RetrievalQuery(
                    query_id=f"Q{len(queries) + 1}", family="endpoint", query=precision,
                    source_fields=(*lexical_sources, "pico.outcome"),
                    relation_semantics=claim.claim_type,
                ))
                if pico and pico.population and _tokens(pico.population):
                    queries.append(RetrievalQuery(
                        query_id=f"Q{len(queries) + 1}", family="endpoint",
                        query=f"{precision} AND ({_lexical_terms(pico.population)})",
                        source_fields=(*lexical_sources, "pico.outcome", "pico.population"),
                        relation_semantics=claim.claim_type,
                    ))
            if outcome_entity and outcome and (
                set(_tokens(_outcome_search_text(outcome)))
                - set(_tokens(outcome_entity.surface_text))
            ):
                # A broad linked outcome ("Muscles") must not erase an
                # asserted qualifier such as "growth", regardless of whether
                # the exposure was also linked. Keep this bounded variant.
                specific = f"({left}) AND ({_lexical_terms(_outcome_search_text(outcome))})"
                queries.append(RetrievalQuery(
                    query_id=f"Q{len(queries) + 1}", family="lexical", query=specific,
                    source_fields=(lexical_sources[0], "pico.outcome"),
                    relation_semantics=claim.claim_type,
                ))
            numbers = tuple(dict.fromkeys(_NUMERIC.findall(claim.raw_text)))[:2]
            if numbers:
                numeric_terms = " AND ".join(
                    f'"{number.replace(" ", "")}"[Title/Abstract]' for number in numbers
                )
                queries.append(RetrievalQuery(
                    query_id=f"Q{len(queries) + 1}", family="distinctive",
                    query=f"{lexical} AND ({numeric_terms})",
                    source_fields=(*lexical_sources, "raw_text"),
                    relation_semantics=claim.claim_type,
                ))
            if not any(query.family == "mesh" for query in queries):
                # PubMed's official Automatic Term Mapping can recover a
                # source term absent from Title/Abstract. A confident two-
                # concept MeSH query already supplies this broader recall.
                automatic = f"({' '.join(_tokens(exposure_term))}) AND " \
                            f"({' '.join(_tokens(_outcome_search_text(outcome_term)))})"
                queries.append(RetrievalQuery(
                    query_id=f"Q{len(queries) + 1}", family="automatic", query=automatic,
                    source_fields=(*lexical_sources, "pubmed_automatic_term_mapping"),
                    relation_semantics=claim.claim_type,
                ))
                variants = lay_variants(outcome_term)
                if variants:
                    # Search-only variants are explicit in query provenance.
                    # The exact outcome remains unchanged in PICO and report.
                    variant_terms = " OR ".join(
                        f'"{variant}"[Title/Abstract]' for _, variant in variants
                    )
                    queries.append(RetrievalQuery(
                        query_id=f"Q{len(queries) + 1}", family="lay_variant",
                        query=f"({left}) AND ({variant_terms})",
                        source_fields=(*lexical_sources, *(
                            f"retrieval_lay_variant:{word}" for word, _ in variants
                        )),
                        relation_semantics=claim.claim_type,
                    ))
    if not queries:
        fallback_words = _tokens(claim.raw_text)
        if fallback_words:
            queries.append(RetrievalQuery(
                query_id="Q1", family="lexical",
                query=" AND ".join(f'"{word}"[Title/Abstract]' for word in fallback_words[:4]),
                source_fields=("raw_text",), relation_semantics=claim.claim_type,
            ))
        warnings.append("structured_terms_incomplete")
    return QueryPlan(claim_type=claim.claim_type, queries=tuple(queries), warnings=tuple(warnings))
