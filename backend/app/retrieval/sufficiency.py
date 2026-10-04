"""Question-specific design eligibility; never source-to-claim support direction."""

import re
from typing import Literal, cast

from app.retrieval.models import ClaimSnapshot, FrozenModel, PubMedDocument

QuestionCategory = Literal[
    "harmful_exposure_causality", "intervention_causality", "treatment", "prevention",
    "diagnostic", "association", "other",
]


class EvidenceDesignFact(FrozenModel):
    document_id: str
    analysis_design: str
    exposure_assignment: str
    source_kind: str
    document_purpose: str | None = None
    role: str
    integrity: str
    currency: str | None = None
    independence_group: str
    underlying_pmids: tuple[str, ...] = ()


def question_category(claim: ClaimSnapshot) -> QuestionCategory:
    if claim.claim_type in {"treatment", "prevention", "diagnostic", "association"}:
        return cast(QuestionCategory, str(claim.claim_type))
    if claim.claim_type == "causal":
        # Reviewed question taxonomy, not condition→verdict or positive direction.
        # Unknown exposures keep conservative intervention-design requirements.
        exposure = claim.pico.intervention_or_exposure if claim.pico else ""
        if re.search(r"\b(?:smoking|tobacco|asbestos|lead exposure|air pollution|"
                     r"ionizing radiation|hypertension|high blood pressure)\b",
                     exposure or "", re.I):
            return "harmful_exposure_causality"
        return "intervention_causality"
    return "other"


def design_fact(doc: PubMedDocument) -> EvidenceDesignFact:
    analysis = doc.relationship_analysis
    meta = doc.authoritative
    return EvidenceDesignFact(
        document_id=doc.document_id,
        analysis_design=analysis.analysis_design if analysis else "unknown",
        exposure_assignment=analysis.exposure_assignment if analysis else "unknown",
        source_kind=doc.source_kind, document_purpose=meta.document_purpose if meta else None,
        role=doc.evidence_role_hint or "incompatible", integrity=doc.integrity.status,
        currency=meta.currency if meta else None,
        independence_group=meta.independence_group if meta else doc.document_id,
        underlying_pmids=meta.underlying_pmids if meta else (),
    )


def independent_source_count(facts: tuple[EvidenceDesignFact, ...]) -> int:
    groups: set[str] = set()
    covered = {f"pubmed:{p}" for f in facts for p in f.underlying_pmids}
    for fact in facts:
        if fact.document_id not in covered:
            groups.add(fact.independence_group)
    return len(groups)


def design_eligible(category: QuestionCategory, fact: EvidenceDesignFact) -> bool:
    if fact.role != "direct" or fact.integrity not in {"valid", "corrected", "updated"}:
        return False
    if fact.source_kind == "authoritative_public_health":
        if fact.currency != "current":
            return False
        # A current press release, general recommendation or fact sheet never
        # satisfies the causal gate just because its publisher is authoritative.
        return (category == "harmful_exposure_causality" and fact.document_purpose in {
            "causal_assessment", "systematic_evidence_summary",
        }) or (category in {"treatment", "prevention", "intervention_causality"}
               and fact.document_purpose == "systematic_evidence_summary")
    if category in {"harmful_exposure_causality", "intervention_causality",
                    "treatment", "prevention"}:
        return (fact.analysis_design == "randomized_intervention"
                and fact.exposure_assignment == "randomized") or (
                    fact.analysis_design in {"systematic_review", "meta_analysis"})
    # Diagnostic claims need explicit diagnostic evidence, not topic/source prestige.
    if category == "diagnostic":
        return fact.analysis_design == "diagnostic_accuracy"
    return category in {"association", "other"}
