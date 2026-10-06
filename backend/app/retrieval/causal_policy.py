"""Versioned causal eligibility from question semantics and frozen source facts.

Eligibility supplies neither direction nor scope. Reviewed assertions must be
explicit and finding-bound; ordinary opinion and association alone remain context.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.retrieval.directness import _aliases, _sentences
from app.retrieval.models import ClaimSnapshot, PubMedDocument

if TYPE_CHECKING:
    from app.retrieval.sufficiency import EvidenceDesignFact

POLICY = "question-evidence-2.1"
ETIOLOGIC = {"etiologic_exposure_causality", "disease_transmission"}
_MANIPULATION = re.compile(
    r"\b(?:lowering|reducing|treating|treatment|therapy|supplementation|vaccination|"
    r"vaccines?|antibiotics?|medication|taking|administering|cessation|quitting)\b",
    re.I,
)
_TRANSMISSION = re.compile(r"\b(?:transmi\w*|spread(?:s|ing)?|contract(?:ed|ing)?)\b", re.I)
_ASSESSMENT = re.compile(
    r"\b(?:causes?|caused|causal|etiologic\w*|carcinogen\w*|transmits?|spreads?|"
    r"(?:is|are|isn['\u2019]t|aren['\u2019]t|cannot|can not|not)\s+"
    r"(?:not\s+)?(?:transmitted|spread)|does?\s+not\s+(?:transmit|spread)|"
    r"(?:transmission|spread)\b.{0,140}\b(?:nonexistent|impossible|ruled out))\b",
    re.I,
)
_SPECULATIVE = re.compile(
    r"\b(?:may|might|could|hypothes\w*|speculat\w*|opinion|believe|"
    r"causality cannot|causality could not|causal effect cannot|not established|"
    r"no evidence|insufficient evidence|absence of evidence|not mentioned|unproven)\b",
    re.I,
)


def question_kind(claim: ClaimSnapshot, fallback: str) -> str:
    if claim.claim_type != "causal" or fallback == "laboratory_experiment":
        return fallback
    exposure = claim.pico.intervention_or_exposure if claim.pico else ""
    # Manipulation of a natural risk factor is an intervention question.
    if _MANIPULATION.search(exposure or ""):
        return "intervention_causality"
    if _TRANSMISSION.search(claim.standalone_text):
        return "disease_transmission"
    natural = any(
        e.entity_type == "intervention_or_exposure"
        and e.mesh_id
        and not e.ambiguous
        and (e.confidence or 0) >= 0.9
        and e.match_type in {"exact", "synonym"}
        and any(t.startswith(("C", "B")) for t in e.tree_numbers)
        for e in claim.entities
    )
    if natural or fallback == "harmful_exposure_causality":
        return "etiologic_exposure_causality"
    return fallback


def _concept(text: str, terms: tuple[str, ...]) -> bool:
    return any(
        all(
            re.search(r"(?<!\w)" + re.escape(w) + r"(?:s|es)?(?!\w)", text, re.I)
            for w in re.findall(r"[^\W_]+", term)
        )
        for term in terms
        if term
    )


def assessment_facts(
    doc: PubMedDocument,
    claim: ClaimSnapshot,
    finding: str,
    quotes: tuple[str, ...],
    *,
    disclaimer_guard: bool = True,
) -> dict[str, object]:
    """Freeze actual evidence/conclusion language, never publisher prestige.

    Only cited text can establish the finding's assessment. General document
    methods supply evidence components, but cannot invent its exposure/endpoint.
    """
    exposure, outcome = _aliases(claim, "intervention_or_exposure"), _aliases(claim, "outcome")
    if not (_concept(finding, exposure) and _concept(finding, outcome)):
        return {}
    assertion = next(
        (
            q
            for q in quotes
            if doc.authoritative
            and doc.authoritative.document_purpose == "transmission_assessment"
            and doc.authoritative.extraction_version == "approved-html-1.1"
            and re.match(
                r".{1,80}\b(?:isn['\u2019]t|is not|cannot|not)\s+"
                r"(?:transmitted|spread)\s+(?:by|through)\b",
                q,
                re.I,
            )
            and _concept(q, exposure)
            and _concept(q, outcome)
        ),
        None,
    )
    for quote in quotes:
        sentences = _sentences(quote)
        for i, sentence in enumerate(sentences):
            context = " ".join(sentences[max(0, i - 2) : i + 1])
            if (
                _concept(context, exposure)
                and _concept(context, outcome)
                and _ASSESSMENT.search(sentence)
                and not _SPECULATIVE.search(sentence)
            ):
                assertion = context
                break
        if assertion:
            break
    if not assertion:
        return {}
    text = " ".join(s.text for s in doc.abstract_sections)
    components = []
    if disclaimer_guard and any(
        re.search(
            r"(?:causal(?:ity)?|cause and effect)\s+(?:cannot|could not|can not|"
            r"not|was not)\s+(?:be\s+)?(?:inferred|established|determined)",
            q,
            re.I,
        )
        for q in quotes
    ):
        components.append("causality_disclaimed")
    if doc.authoritative and doc.authoritative.document_purpose in {
        "causal_assessment",
        "systematic_evidence_summary",
        "transmission_assessment",
    }:
        components.append("reviewed_assessment")
    if doc.relationship_analysis and doc.relationship_analysis.analysis_design in {
        "prospective_cohort",
        "case_control",
    }:
        components.append("primary_epidemiology")
    if re.search(r"\b(?:cohort|case[- ]control|epidemiolog\w*)\b", text, re.I):
        components.append("epidemiology")
    if re.search(
        r"\b(?:prospective|follow[- ]up|preced\w*|before onset|temporality)\b", text, re.I
    ):
        components.append("temporality")
    if re.search(r"\b(?:mechanis\w*|replicat\w*|receptors?|oncogen\w*)\b", text, re.I):
        components.append("mechanism")
    if re.search(r"\bexperimental evidence\b", text, re.I):
        components.append("experimental_evidence")
    if re.search(r"\bprobability estimates?\b", text, re.I):
        components.append("probability_assessment")
    if doc.study_design in {"review", "systematic_review", "meta_analysis"}:
        components.append("synthesis_document")
    if re.search(
        r"\b(?:studies (?:have )?(?:shown|demonstrated|found)|"
        r"evidence (?:obtained|from)|observational evidence)\b",
        text,
        re.I,
    ):
        components.append("empirical_findings")
    return {"causal_assessment_text": assertion, "causal_evidence_components": tuple(components)}


def eligible_fact(
    category: str, fact: EvidenceDesignFact, peers: tuple[EvidenceDesignFact, ...] = (),
    *, clinical_legacy: bool = False,
) -> bool | None:
    if fact.role != "direct" or fact.integrity not in {"valid", "corrected", "updated"}:
        return False
    if category in ETIOLOGIC:
        if "causality_disclaimed" in (fact.causal_evidence_components or ()):
            return False
        # Validated randomized evidence remains eligible; this policy adds
        # appropriate nonrandomized routes instead of replacing that evidence.
        if (
            fact.analysis_design == "randomized_intervention"
            and fact.exposure_assignment == "randomized"
            or fact.analysis_design in {"systematic_review", "meta_analysis"}
            and fact.synthesis_randomized_trials is True
            or fact.analysis_design == "causal_evidence_synthesis"
            and fact.completed_randomized_result_synthesis is True
        ):
            return True
        if not fact.causal_assessment_text:
            return False
        components = set(fact.causal_evidence_components or ())
        if fact.source_kind == "authoritative_public_health":
            return (
                fact.currency == "current"
                and "reviewed_assessment" in components
                and fact.document_purpose
                in {"causal_assessment", "systematic_evidence_summary", "transmission_assessment"}
                and (
                    category == "disease_transmission"
                    or fact.document_purpose != "transmission_assessment"
                )
            )
        # An explicit review conclusion needs converging empirical components.
        # Mechanism, a lone review assertion or a survey of beliefs is insufficient.
        if (
            fact.analysis_design in {"systematic_review", "meta_analysis", "unknown"}
            and "synthesis_document" in components
        ):
            if category == "disease_transmission":
                return {
                    "mechanism",
                    "experimental_evidence",
                    "probability_assessment",
                } <= components
            return {"epidemiology", "temporality", "mechanism", "empirical_findings"} <= components
        if (
            fact.analysis_design in {"prospective_cohort", "case_control"}
            and fact.exposure_assignment == "observed"
        ):
            studies = [
                f
                for f in (fact, *peers)
                if f.role == "direct"
                and f.integrity in {"valid", "corrected", "updated"}
                and f.causal_assessment_text
                and f.exposure_assignment == "observed"
                and f.analysis_design in {"prospective_cohort", "case_control"}
            ]
            return len({f.independence_group for f in studies}) >= 2 and any(
                "temporality" in (f.causal_evidence_components or ()) for f in studies
            )
        return False
    if not clinical_legacy and category in {"intervention_causality", "treatment", "prevention"}:
        return (fact.analysis_design == "randomized_intervention"
                and fact.exposure_assignment == "randomized") or (
                    fact.analysis_design in {"systematic_review", "meta_analysis"}
                    and fact.synthesis_randomized_trials is True) or (
                    fact.analysis_design == "causal_evidence_synthesis"
                    and fact.completed_randomized_result_synthesis is True)
    return None  # Current clinical policy retains the established intervention safeguards.
