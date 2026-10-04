"""Independent evidence axes and a pure, versioned V2 proposal qualifier."""

import re
from typing import Literal

from pydantic import Field

from app.validation.models import FrozenModel
from app.validation.qualification import (
    ConclusionQualification,
    ConclusionQualifierInput,
    FindingQualificationInput,
    qualify_conclusion,
)
from app.validation.relations import ClaimRelationAssessment

VERSION = "evidence-claim-axes-1.0"
QUALIFIER_VERSION = "conclusion-qualifier-1.4"
QUALIFIER_VERSIONS = {"conclusion-qualifier-1.2", "conclusion-qualifier-1.3", QUALIFIER_VERSION}


def null_precision_reason(texts: tuple[str, ...]) -> str:
    """A necessary source-text signal for a precise null, with audit-friendly cause."""
    text = " ".join(texts)
    if re.search(
        r"\b(?:wide|imprecise|underpowered)\b|"
        r"\bspanning (?:benefit and harm|harm and benefit)", text, re.I,
    ):
        return "wide_or_imprecise_interval"
    if re.search(r"\b(?:did not|does not|cannot|could not|not)\s+"
                 r"(?:be\s+)?exclud(?:e|ed)\b|"
                 r"\b(?:equivalence|noninferiority)\s+was\s+not\s+established\b|"
                 r"\b(?:failed|did not)\s+(?:to\s+)?(?:establish|show)\s+equivalence\b",
                 text, re.I):
        return "source_does_not_exclude_effect"
    if re.search(r"\b(?:established|demonstrated|confirmed)\s+"
                 r"(?:equivalence|noninferiority|non-inferiority)\b|"
                 r"\bequivalent\s+within\b", text, re.I):
        return "source_reports_equivalence"
    if re.search(r"\b(?:narrow (?:confidence )?interval.{0,100}(?:excluded|ruled out)|"
                 r"precisely? (?:excluded|ruled out)|"
                 r"excluded? (?:a |the )?(?:material|clinically relevant) effect|"
                 r"ruled out material effects?)\b", text, re.I):
        return "source_excludes_material_effect"
    if re.search(r"\b(?:nonsignificant|not significant|no significant)\b", text, re.I):
        return "nonsignificance_only"
    return "no_source_precision_signal"


def precision_grounded(texts: tuple[str, ...]) -> bool:
    """Conservative necessary lexical check, not proof of clinical equivalence."""
    if null_precision_reason(texts) not in {"source_reports_equivalence",
                                             "source_excludes_material_effect"}:
        return False
    text = " ".join(texts)
    for match in re.finditer(
        r"\b(?:equivalence|equivalent|precise(?:ly)?|narrow (?:confidence )?intervals?|"
        r"ruled? out)\b", text, re.I,
    ):
        context = (text[max(0, match.start() - 25):match.start()] + " " +
                   text[match.end():match.end() + 25])
        if not re.search(r"\b(?:no|not|cannot|could not|without)\b", context, re.I):
            return True
    return bool(re.search(r"\b(?:equivalence|equivalent|noninferiority|non-inferiority|"
                          r"narrow (?:confidence )?interval|excluded?|ruled? out)\b", text, re.I))


def _precision_grounded_13(texts: tuple[str, ...]) -> bool:
    text = " ".join(texts)
    for match in re.finditer(
        r"\b(?:equivalence|equivalent|precise(?:ly)?|narrow (?:confidence )?intervals?|"
        r"ruled? out)\b", text, re.I,
    ):
        context = (text[max(0, match.start() - 25):match.start()] + " " +
                   text[match.end():match.end() + 25])
        if not re.search(r"\b(?:no|not|cannot|could not|without)\b", context, re.I):
            return True
    return False


def gradient_kind(texts: tuple[str, ...]) -> str:
    """Classify an explicit contrast only; lack of a control arm is not a mismatch."""
    text = " ".join(texts)
    if re.search(r"\b(?:versus|vs\.?|compared with)\s+(?:an?\s+)?"
                 r"(?:unrelated\s+)?(?:alternative|active)\s+"
                 r"(?:treatment|therapy|drug)\b", text, re.I):
        return "alternative_comparator"
    if re.search(r"\b(?:high(?:er)?[ -]dose|low(?:er)?[ -]dose|\d+\s*(?:mg|g))\b", text, re.I):
        return "dose_gradient"
    if re.search(r"\b(?:daily\b.{0,100}\bdiscretionary|discretionary\b.{0,100}\bdaily|"
                 r"(?:more|greater|higher|frequent)\b.{0,100}\b(?:less|lesser|lower|infrequent)|"
                 r"(?:less|lesser|lower|infrequent)\b.{0,100}\b(?:more|greater|higher|frequent))\b",
                 text, re.I | re.S):
        return "same_exposure_gradient"
    return "unknown"


class EvidenceClaimAssessment(FrozenModel):
    statement_id: str = Field(pattern=r"^S[1-5]$")
    direction: Literal["supports_claim", "opposes_claim", "neutral", "mixed", "unclear"]
    scope: Literal["aligned", "compatible_but_narrower", "broader_or_indirect",
                   "incompatible", "uncertain"]
    strength: Literal["decisive", "strong", "supporting", "weak", "insufficient", "uncertain"]
    role: Literal["direct", "synthesis", "contextual", "mechanistic", "background", "uncertain"]
    scope_basis: Literal["same_question", "exposure_gradient", "population", "dose",
                         "active_alternative", "endpoint", "other", "uncertain"]
    finding_basis: Literal["direct_result", "causal_assessment", "association",
                           "imprecise_null", "precise_null", "conflicting_results",
                           "reverse_causation", "context", "uncertain"]
    reason: str = Field(min_length=1, max_length=1200)


class AxesQualifierInput(FrozenModel):
    # Existing sufficiency/design/numeric/risk rules remain part of the input.
    base: ConclusionQualifierInput
    assessments: tuple[EvidenceClaimAssessment, ...]
    comparator: str | None
    exact_claim: str
    source_texts: dict[str, tuple[str, ...]]
    # Set only by numeric-fidelity-comparability-1.0. Absent in historical audits.
    magnitude_eligible: dict[str, bool] | None = Field(default=None,
                                                     exclude_if=lambda value: value is None)


class AxesQualificationAudit(FrozenModel):
    version: str = QUALIFIER_VERSION
    input: AxesQualifierInput
    output: ConclusionQualification


def gradient_compatible(data: AxesQualifierInput, item: EvidenceClaimAssessment,
                        *, version: str = QUALIFIER_VERSION) -> bool:
    """Narrow exception for an actually tested same-exposure intensity contrast.

    Unspecified != zero exposure. Does not admit untested doses/subgroups or an
    alternative treatment. Semantic endpoint/exposure fit still must pass.
    """
    if data.comparator is not None or item.scope_basis not in {"exposure_gradient", "dose"}:
        return False
    if not re.search(r"\b(?:frequent|frequency|regular|daily|greater|more|higher|intens\w*)\b",
                     data.exact_claim, re.I):
        return False
    if version != QUALIFIER_VERSION:
        source = " ".join(data.source_texts.get(item.statement_id, ()))
        return bool(re.search(
            r"\b(?:daily\b.{0,100}\bdiscretionary|discretionary\b.{0,100}\bdaily|"
            r"(?:more|greater|higher)\b.{0,100}\b(?:less|lesser|lower)|"
            r"(?:less|lesser|lower)\b.{0,100}\b(?:more|greater|higher))\b",
            source, re.I | re.S,
        ))
    return gradient_kind(data.source_texts.get(item.statement_id, ())) == "same_exposure_gradient"


def mapped_relations(data: AxesQualifierInput, *, version: str = QUALIFIER_VERSION
                     ) -> tuple[ClaimRelationAssessment, ...]:
    """Bridge only for NEW audits. Original axes remain unchanged and auditable."""
    findings: dict[str, FindingQualificationInput] = {f.statement_id: f for f in data.base.findings}
    result: list[ClaimRelationAssessment] = []
    for item in data.assessments:
        scope = "mismatch" if item.scope == "incompatible" else item.scope
        relation = {"supports_claim": "supports_claim", "opposes_claim": "contradicts_claim",
                    "neutral": "insufficient", "mixed": "uncertain", "unclear": "uncertain"
                    }[item.direction]
        materiality = "supporting"
        if item.role in {"contextual", "mechanistic", "background"}:
            relation, materiality = "context_only", "contextual"
        elif item.role == "uncertain" or item.strength == "uncertain":
            materiality = "uncertain"
        elif (version in {"conclusion-qualifier-1.3", QUALIFIER_VERSION}
              and item.finding_basis == "precise_null"
              and not (precision_grounded(data.source_texts.get(item.statement_id, ()))
                       if version == QUALIFIER_VERSION else
                       _precision_grounded_13(data.source_texts.get(item.statement_id, ())))):
            # A model's 'precise null' label is not proof of effect exclusion.
            # Preserve its raw axes; without affirmative frozen exclusion/precision
            # this finding cannot supply a decisive opposite vote.
            relation = "insufficient"
        elif item.finding_basis in {"imprecise_null", "reverse_causation"} or (
            item.strength in {"weak", "insufficient"}
        ):
            relation = "insufficient"
        elif item.finding_basis == "conflicting_results":
            relation = "uncertain"
        elif item.strength in {"decisive", "strong"} and item.role in {"direct", "synthesis"}:
            # Strong direction is a candidate, never a design/provenance exemption.
            if item.scope == "aligned" or (item.scope == "compatible_but_narrower"
                                           and (item.scope_basis == "exposure_gradient" or
                                                version == QUALIFIER_VERSION)
                                           and gradient_compatible(data, item, version=version)):
                materiality = "decisive"
        # Unknown/unmatched IDs cannot supply design; base validation rejects them.
        if item.statement_id not in findings:
            materiality = "uncertain"
        if (data.magnitude_eligible is not None
                and data.magnitude_eligible.get(item.statement_id) is False
                and relation in {"supports_claim", "contradicts_claim"}):
            # Verified but noncomparable quantities cannot supply a magnitude vote.
            # Keep source attribution and all original semantic axes untouched.
            relation, materiality = "insufficient", "supporting"
        result.append(ClaimRelationAssessment.model_validate({
            "statement_id": item.statement_id, "relation": relation,
            "scope": scope, "materiality": materiality, "reason": item.reason,
        }))
    return tuple(result)


def qualify_axes(data: AxesQualifierInput, *, version: str = QUALIFIER_VERSION
                 ) -> ConclusionQualification:
    # Never flip the judge's proposal; unchanged threshold/claim design policy.
    if version not in QUALIFIER_VERSIONS:
        raise ValueError("Unknown axes qualifier version")
    return qualify_conclusion(data.base.model_copy(
        update={"relations": mapped_relations(data, version=version)}))
