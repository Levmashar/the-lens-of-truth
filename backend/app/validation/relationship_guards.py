"""Versioned, source-owned comparability guards; never manufacture a direction."""

import re

from app.judging.models import JudgeDecisionV2, JudgeRun
from app.retrieval.lexical import lay_variants
from app.retrieval.models import EvidencePack
from app.validation.axes import AxesQualifierInput, EvidenceClaimAssessment
from app.validation.models import FrozenModel


class RelationshipContext(FrozenModel):
    exposure_terms: tuple[str, ...]
    outcome_terms: tuple[str, ...]
    finding_texts: dict[str, str]
    source_contexts: dict[str, str] = {}
    disease_onset: bool
    population: str | None = None


def relationship_context(judge: JudgeRun, pack: EvidencePack, *, scope_polarity: bool = False
                         ) -> dict[str, object]:
    assert isinstance(judge.decision, JudgeDecisionV2)
    claim = pack.claim_snapshot
    pico = claim.pico
    passages = {p.evidence_id: p for p in pack.passages}
    documents = {d.document_id: d for d in pack.documents}

    def terms(role: str) -> tuple[str, ...]:
        literal = getattr(pico, role) if pico else None
        aliases = tuple(
            term
            for e in claim.entities
            if e.entity_type == role
            and e.mesh_id
            and not e.ambiguous
            and (e.confidence or 0) >= 0.9
            for term in (e.surface_text, e.preferred_name)
            if term
        )
        search_terms = tuple(v for _, v in lay_variants(literal)) if role == "outcome" else ()
        return tuple(dict.fromkeys(((literal,) if literal else ()) + aliases + search_terms))

    onset = (
        claim.claim_type in {"causal", "prevention"}
        and bool(
            re.search(
                r"\b(?:causes?|risk|incidence|develop(?:ment|ing)?|prevents?)\b",
                claim.standalone_text,
                re.I,
            )
        )
        and not re.search(
            r"\b(?:progression|severity|duration|recurrence|relapse)\b",
            pico.outcome or "" if pico else "",
            re.I,
        )
    )
    context = RelationshipContext(
        exposure_terms=terms("intervention_or_exposure"),
        outcome_terms=terms("outcome"),
        disease_onset=bool(onset),
        finding_texts={s.statement_id: s.text for s in judge.decision.statements},
        source_contexts={
            s.statement_id: " ".join(
                f"{documents[passages[r.evidence_id].passage.document_id].title} "
                + " ".join(documents[passages[r.evidence_id].passage.document_id].mesh_terms)
                for r in s.evidence_refs
            )
            for s in judge.decision.statements
        },
    ).model_dump(mode="json")
    context.pop("population")
    if scope_polarity:
        context["population"] = pico.population if pico else None
    return context


def contains_concept(text: str, terms: tuple[str, ...]) -> bool:
    # Necessary concept presence, not direction or proof of endpoint equivalence.
    # Inflection and reordered nouns ("cancers of the lung") are still present.
    return any(
        all(
            re.search(r"(?<!\w)" + re.escape(word) + r"(?:s|es)?(?!\w)", text, re.I)
            for word in term.split()
        )
        for term in terms
        if term
    )


_CELL_TREATMENT = re.compile(
    r"\b(?:apoptosis|cytotoxic(?:ity)?|kill(?:s|ing|ed)?|inhibit(?:s|ed|ion)?|"
    r"anti[- ]?(?:cancer|tumou?r|leukemic)|anti[- ]?proliferative)\b",
    re.I,
)
_CELL_SUBJECT = re.compile(r"\b(?:cells?|cell[- ]lines?|in vitro|proliferation)\b", re.I)
_TREATMENT_ENDPOINT_13 = re.compile(
    r"\b(?:treat(?:ing|ment|ed|s)?|therap(?:y|eutic)|slow(?:s|ing|ed)?|progression|"
    r"diagnostic|diagnos(?:ing|ed)|detection|screening)\b",
    re.I,
)
_ONSET_ENDPOINT = re.compile(
    r"\b(?:causes?|incident|incidence|risk|prevention|new cases|new[- ]onset|developing|"
    r"primary prevention|risk of develop)\b",
    re.I,
)
_AGGREGATE_SOURCE = re.compile(
    r"\b(?:ecological|population[- ]level|global burden|GBD|DALYs|"
    r"disability[- ]adjusted|time[- ]trends?|time[- ]series)\b",
    re.I,
)
_TREND_FINDING_13 = re.compile(
    r"\b(?:trend|rank(?:ed|ing)?|declin(?:e|ed|ing)|"
    r"mortality|leading risk factor|burden|over the same period)\b",
    re.I,
)
_TREATMENT_ENDPOINT = re.compile(
    _TREATMENT_ENDPOINT_13.pattern.replace("diagnos(?:ing|ed)", "diagnos(?:is|ing|ed)"), re.I,
)
_TREND_FINDING = re.compile(
    r"\b(?:trends?|rank(?:ed|ing)?|declin(?:e|ed|ing)|over the same period)\b", re.I,
)
_ABSENCE_INFERENCE = re.compile(
    r"\b(?:does not mention|not mentioned|no mention|omits?|omission|not listed|"
    r"absence of mention|alternative (?:known )?cause|another (?:known )?cause)\b",
    re.I,
)


def guarded_axes(
    data: AxesQualifierInput, *, legacy: bool = False, scope_polarity: bool = True,
) -> tuple[
    tuple[EvidenceClaimAssessment, ...],
    dict[str, tuple[str, ...]],
]:
    if data.relationship_context is None:
        raise ValueError("Missing versioned relationship context")
    context = RelationshipContext.model_validate(data.relationship_context)
    treatment_endpoint = _TREATMENT_ENDPOINT_13 if legacy else _TREATMENT_ENDPOINT
    trend_finding = _TREND_FINDING_13 if legacy else _TREND_FINDING
    findings = {f.statement_id: f for f in data.base.findings}
    guarded = []
    reasons = {}
    for axis in data.assessments:
        text = context.finding_texts.get(axis.statement_id, "")
        source = " ".join(data.source_texts.get(axis.statement_id, ()))
        concept_text = source + " " + context.source_contexts.get(axis.statement_id, "")
        codes = []
        adjustments = []
        incompatible = False
        if context.disease_onset and (
            (_CELL_TREATMENT.search(text) and _CELL_SUBJECT.search(text))
            or (
                _CELL_TREATMENT.search(source)
                and _CELL_SUBJECT.search(source)
                and not _ONSET_ENDPOINT.search(source)
            )
            or (treatment_endpoint.search(text) and not _ONSET_ENDPOINT.search(text))
            or (treatment_endpoint.search(source) and not _ONSET_ENDPOINT.search(source))
        ):
            codes.append("DISEASE_STAGE_ENDPOINT_MISMATCH")
            incompatible = True
        if axis.direction == "opposes_claim":
            if context.exposure_terms and not contains_concept(
                concept_text, context.exposure_terms
            ):
                codes.append("CLAIMED_EXPOSURE_NOT_ESTABLISHED")
            if context.outcome_terms and not contains_concept(concept_text, context.outcome_terms):
                codes.append("CLAIMED_ENDPOINT_NOT_ESTABLISHED")
            if _ABSENCE_INFERENCE.search(text):
                codes.append("ABSENCE_OR_ALTERNATIVE_CAUSE_IS_CONTEXT")
            if (
                data.base.claim_type == "causal"
                and _AGGREGATE_SOURCE.search(source)
                and trend_finding.search(text)
            ):
                codes.append("ECOLOGICAL_TREND_IS_CONTEXT")
        if not codes and scope_polarity:
            from app.validation.polarity import checked_direction

            direction = checked_direction(data.exact_claim, text,
                                          data.source_texts.get(axis.statement_id, ()), context)
            if (direction and axis.direction in {"supports_claim", "opposes_claim"}
                    and axis.direction != direction):
                axis = axis.model_copy(update={"direction": direction})
                adjustments.append("SOURCE_GROUNDED_POLARITY_CORRECTION")
            # Existential treatment claims do not assert efficacy in every
            # population. Keep restrictions for universal/quantified claims,
            # different endpoints, active comparators and specified populations.
            if (data.base.claim_type == "treatment" and context.population is None
                    and data.comparator is None and not data.magnitude_eligible
                    and re.search(r"\bcan\s+(?:treat|cure|relieve|improve)\b",
                                  data.exact_claim, re.I)
                    and not re.search(r"\b(?:all|every|always|completely|permanently)\b",
                                      data.exact_claim, re.I)
                    and axis.direction == "supports_claim"
                    and axis.scope == "compatible_but_narrower"
                    and axis.scope_basis == "population"
                    and contains_concept(concept_text, context.outcome_terms)):
                axis = axis.model_copy(update={"scope": "aligned", "scope_basis": "same_question"})
                adjustments.append("EXISTENTIAL_TREATMENT_POPULATION_COMPATIBLE")
            if (axis.statement_id in findings and axis.scope == "aligned"
                    and axis.direction in {"supports_claim", "opposes_claim"}
                    and axis.finding_basis in {"direct_result", "causal_assessment"}
                    and axis.strength in {"supporting", "strong", "decisive"}
                    and any(f.experimental_assignment_text for f in
                            findings[axis.statement_id].evidence_design_facts)
                    and axis.role in {"mechanistic", "contextual"}):
                axis = axis.model_copy(update={"role": "direct"})
                adjustments.append("FINDING_BOUND_EXPERIMENTAL_RESULT")
            if (data.base.evidence_policy in {"question-evidence-2.0", "question-evidence-2.1"}
                    and data.base.question_category in {
                        "etiologic_exposure_causality", "disease_transmission"}
                    and axis.statement_id in findings and axis.scope == "aligned"
                    and axis.direction in {"supports_claim", "opposes_claim"}
                    and axis.finding_basis == "causal_assessment"
                    and axis.strength in {"strong", "decisive"}
                    and axis.role in {"contextual", "mechanistic"}):
                from app.retrieval.sufficiency import design_eligible

                if any(f.causal_assessment_text and design_eligible(
                    data.base.question_category, f.model_copy(update={"role": "direct"}),
                    policy=data.base.evidence_policy)
                    for f in findings[axis.statement_id].evidence_design_facts):
                    axis = axis.model_copy(update={"role": "direct"})
                    adjustments.append("FINDING_BOUND_CAUSAL_ASSESSMENT")
        if codes:
            axis = axis.model_copy(
                update={
                    "direction": "neutral",
                    "role": "contextual",
                    **(
                        {"scope": "incompatible", "scope_basis": "endpoint"} if incompatible else {}
                    ),
                }
            )
            reasons[axis.statement_id] = tuple(codes)
        elif (
            axis.role == "contextual"
            and axis.scope == "aligned"
            and axis.strength in {"strong", "decisive"}
            and axis.finding_basis in {"direct_result", "causal_assessment"}
            and axis.direction in {"supports_claim", "opposes_claim"}
            and axis.statement_id in findings
            and any(
                f.completed_randomized_result_synthesis is True
                for f in findings[axis.statement_id].evidence_design_facts
            )
        ):
            axis = axis.model_copy(update={"role": "synthesis"})
            reasons[axis.statement_id] = ("COMPLETED_RANDOMIZED_RESULT_SYNTHESIS",)
        guarded.append(axis)
        if adjustments:
            reasons[axis.statement_id] = (*reasons.get(axis.statement_id, ()), *adjustments)
    return tuple(guarded), reasons
