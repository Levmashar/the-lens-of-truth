"""Conservative, source-anchored exposure assignment classification."""

import re

from app.retrieval.directness import _aliases, _matches, _sentences
from app.retrieval.models import ClaimSnapshot, PubMedDocument, RelationshipAnalysis


def characterize_analysis(claim: ClaimSnapshot, doc: PubMedDocument) -> RelationshipAnalysis:
    methods = tuple(s.text for s in doc.abstract_sections if
                    "METHOD" in (s.label or "").upper() or not s.label)
    aliases = _aliases(claim, "intervention_or_exposure")
    if claim.pico and claim.pico.intervention_or_exposure:
        aliases = (*aliases, claim.pico.intervention_or_exposure)
    # These labels describe explicitly tagged syntheses, not a causal result.
    if doc.study_design in {"meta_analysis", "systematic_review"}:
        if "as topic" in doc.study_design_source:
            return RelationshipAnalysis()  # "As Topic" is not the article's own design.
        return RelationshipAnalysis(
            analysis_design="meta_analysis" if doc.study_design == "meta_analysis"
            else "systematic_review", exposure_assignment="synthesized",
            basis=doc.study_design_source,
        )
    for text in methods:
        for sentence in _sentences(text):
            if not _matches(sentence, aliases):
                continue
            assigned = re.search(
                r"\b(?:randomly assigned|randomi[sz]ed to|randomly allocated)\b", sentence, re.I,
            )
            # An exposure must occur AFTER assignment, not merely elsewhere in
            # the sentence (smokers randomized to supplements is not smoking RCT).
            if assigned and _matches(sentence[assigned.end():], aliases):
                return RelationshipAnalysis(
                    analysis_design="randomized_intervention", exposure_assignment="randomized",
                    basis="explicit_methods_assignment", evidence_text=sentence,
                )
            if re.search(r"\b(?:examined|measured|collected|recorded|reported|assessed)\b",
                         sentence, re.I) and doc.study_design in {
                             "randomized_controlled_trial", "clinical_trial"}:
                return RelationshipAnalysis(
                    analysis_design="secondary_observational_analysis",
                    exposure_assignment="observed", basis="explicit_methods_observation",
                    evidence_text=sentence,
                )
    source = " ".join((doc.title, *methods))
    if (re.search(r"\bdiagnostic accuracy\b", source, re.I)
            and re.search(r"\breference standard\b", source, re.I)):
        return RelationshipAnalysis(
            analysis_design="diagnostic_accuracy", exposure_assignment="observed",
            basis="explicit_methods_reference_standard", evidence_text=source[:1600],
        )
    for pattern, design in (
        (r"\bprospective cohort\b", "prospective_cohort"),
        (r"\bcase.control (?:study|studies|analysis)\b", "case_control"),
        (r"\bcross.sectional\b", "cross_sectional"),
    ):
        if re.search(pattern, source, re.I):
            return RelationshipAnalysis.model_validate({
                "analysis_design": design, "exposure_assignment": "observed",
                "basis": "explicit_title_or_methods", "evidence_text": source[:1600],
            })
    return RelationshipAnalysis()
