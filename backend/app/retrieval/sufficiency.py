"""Question-specific design eligibility; never source-to-claim support direction."""

import re
from typing import Literal, cast

from pydantic import Field

from app.pipeline.setting import laboratory_claim
from app.retrieval.models import ClaimSnapshot, FrozenModel, PubMedDocument

QuestionCategory = Literal[
    "harmful_exposure_causality", "intervention_causality", "treatment", "prevention",
    "diagnostic", "association", "other", "laboratory_experiment",
    "etiologic_exposure_causality", "disease_transmission",
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
    completed_randomized_result_synthesis: bool | None = Field(
        default=None, exclude_if=lambda value: value is None)
    synthesis_randomized_trials: bool | None = Field(
        default=None, exclude_if=lambda value: value is None)
    experimental_assignment_text: str | None = Field(
        default=None, exclude_if=lambda value: value is None)
    causal_assessment_text: str | None = Field(default=None, exclude_if=lambda v: v is None)
    causal_evidence_components: tuple[str, ...] | None = Field(
        default=None, exclude_if=lambda v: v is None)


def question_category(claim: ClaimSnapshot, *, experimental_setting: bool = False,
                      causal_policy: bool = False
                      ) -> QuestionCategory:
    if causal_policy:
        from app.retrieval.causal_policy import question_kind

        return cast(QuestionCategory, question_kind(claim, question_category(
            claim, experimental_setting=experimental_setting)))
    if experimental_setting and laboratory_claim(
        claim.standalone_text, claim.pico.population if claim.pico else None,
    ):
        return "laboratory_experiment"
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


def design_fact(doc: PubMedDocument, *, finding_design: bool = False,
                causal_synthesis: bool = False) -> EvidenceDesignFact:
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
        synthesis_randomized_trials=randomized_synthesis(doc) if finding_design else None,
        completed_randomized_result_synthesis=completed_trial_synthesis(doc)
        if causal_synthesis else None,
    )


def independent_source_count(facts: tuple[EvidenceDesignFact, ...]) -> int:
    groups: set[str] = set()
    covered = {f"pubmed:{p}" for f in facts for p in f.underlying_pmids}
    for fact in facts:
        if fact.document_id not in covered:
            groups.add(fact.independence_group)
    return len(groups)


def design_eligible(category: QuestionCategory, fact: EvidenceDesignFact, *,
                    policy: str = "question-evidence-1.0",
                    peers: tuple[EvidenceDesignFact, ...] = ()) -> bool:
    if policy in {"question-evidence-2.0", "question-evidence-2.1"}:
        from app.retrieval.causal_policy import eligible_fact

        answer = eligible_fact(
            category, fact, peers, clinical_legacy=policy == "question-evidence-2.1"
        )
        if answer is not None:
            return answer
    if fact.role != "direct" or fact.integrity not in {"valid", "corrected", "updated"}:
        return False
    if category == "laboratory_experiment":
        return (fact.analysis_design in {"controlled_laboratory_experiment",
                                        "laboratory_intervention"}
                and fact.exposure_assignment == "experimental"
                and fact.experimental_assignment_text is not None)
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
                    fact.analysis_design in {"systematic_review", "meta_analysis"}) or (
                    fact.analysis_design == "causal_evidence_synthesis"
                    and fact.completed_randomized_result_synthesis is True)
    # Diagnostic claims need explicit diagnostic evidence, not topic/source prestige.
    if category == "diagnostic":
        return fact.analysis_design == "diagnostic_accuracy"
    return category in {"association", "other"}


def randomized_synthesis(doc: PubMedDocument) -> bool | None:
    """Literal trial-method facts from frozen review text, independent of claims."""
    if not doc.relationship_analysis or doc.relationship_analysis.analysis_design not in {
        "systematic_review", "meta_analysis",
    }:
        return None
    text = " ".join(section.text for section in doc.abstract_sections)
    affirmatives = re.finditer(
        r"(?:included|eligible|selected|controlled|clinical|blind|blinded|of|of the|were)\s+"
        r"(?:[a-z-]+\s+){0,4}randomi[sz]ed(?:[ ,;-]+(?:controlled|double-blind|clinical))*"
        r"\s+trials|(?:trials|studies)\s+(?:were|are)\s+randomi[sz]ed", text, re.I,
    )
    for affirmative in affirmatives:
        prefix = re.split(r"random", affirmative.group(), maxsplit=1, flags=re.I)[0]
        if not re.search(r"\b(?:not|non|un)\s*[-]?\s*$", prefix, re.I):
            return True
    return None


def completed_trial_synthesis(doc: PubMedDocument) -> bool | None:
    """A review's explicit completed randomized result, never trial-name prestige."""
    if doc.source_kind != "pubmed" or doc.study_design not in {
        "review", "systematic_review", "meta_analysis",
    }:
        return None
    text = " ".join(s.text for s in doc.abstract_sections) or doc.abstract or ""
    for match in re.finditer(
        r"\brandomi[sz]ed(?:[ -]+(?:controlled|clinical|double-blind))*\s+trials?"
        r"\s+(?:(?:have|has)\s+)?(?:demonstrated|shown|showed|found|established|confirmed)"
        r"\s+[^.!?]{5,220}", text, re.I,
    ):
        prefix = text[max(0, match.start()-15):match.start()]
        if not re.search(r"\b(?:not|non)\s*[-]?\s*$", prefix, re.I) and not re.search(
            r"\b(?:no|not|inconclusive|inconsistent|uncertain)\b", match.group(), re.I,
        ):
            return True
    return None


def finding_experiment(fact: EvidenceDesignFact, doc: PubMedDocument,
                       claim: ClaimSnapshot, finding_text: str, *,
                       laboratory_intervention: bool = False) -> EvidenceDesignFact:
    """Bind a finding to a literal assigned arm, not the parent publication tag.

    A class-wide intervention may name a particular drug in its attributed
    finding. Assignment is established only for that named arm. A risk factor
    measured among trial participants never inherits the arm's design.
    """
    from app.retrieval.directness import _aliases, _matches, _sentences

    methods = tuple(s.text for s in doc.abstract_sections
                    if not s.label or "METHOD" in s.label.upper()) \
        if doc.study_design in {"randomized_controlled_trial", "clinical_trial"} else ()
    for text in methods:
        for sentence in _sentences(text):
            assigned = re.search(
                r"\b(?:randomi[sz]ed|randomly assigned|randomly allocated)\b"
                r"[^.!?]{0,160}?\bto\s+([^();,.\r\n]{1,80})"
                r"(?:\([^)]{0,180}\))?\s+or\s+([^();,.\r\n]{1,80})",
                sentence, re.I,
            )
            if (assigned and doc.study_design in {"randomized_controlled_trial", "clinical_trial"}
                    and not re.search(r"(?:non[- ]|not\s+)$", sentence[:assigned.start()], re.I)
                    and any(_matches(finding_text, (arm.strip(),))
                                for arm in assigned.groups())):
                return fact.model_copy(update={
                    "analysis_design": "randomized_intervention",
                    "exposure_assignment": "randomized",
                    "experimental_assignment_text": sentence,
                })
    if laboratory_claim(claim.standalone_text, claim.pico.population if claim.pico else None):
        exposure = _aliases(claim, "intervention_or_exposure")
        source = " ".join(s.text for s in doc.abstract_sections)
        experimental = bool(re.search(r"\b(?:in this study|we (?:investigated|examined)|"
                                      r"in vitro|assays?)\b", source, re.I))
        if ((laboratory_intervention and experimental
             or re.search(r"\b(?:control|untreated|unexposed|non[- ]irradiated)\b", source, re.I))
                and (not laboratory_intervention or doc.study_design not in {
                    "review", "systematic_review", "meta_analysis"})
                and _matches(finding_text, exposure)):
            for sentence in _sentences(source):
                if (_matches(sentence, exposure)
                        and (not laboratory_intervention or not re.search(
                            r"\b(?:will|planned|protocol|may|might|could|reviewed|review|"
                            r"hypothesi[sz]ed)\b", sentence, re.I))
                        and re.search(r"\b(?:cells?|cell[- ]lines?|in vitro)\b", sentence, re.I)
                        and re.search(r"\b(?:exposed|irradiat\w*|treated|induc\w*|applied)\b",
                                      sentence, re.I)):
                    return fact.model_copy(update={
                        "analysis_design": "laboratory_intervention" if laboratory_intervention
                        else "controlled_laboratory_experiment",
                        "exposure_assignment": "experimental",
                        "experimental_assignment_text": sentence,
                    })
    return fact
