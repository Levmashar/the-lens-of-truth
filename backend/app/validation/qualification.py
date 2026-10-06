"""Pure label qualification from attributed findings and explicit claim relations."""

from enum import StrEnum
from typing import Literal

from app.judging.models import JudgeLabel
from app.pipeline.claim_types import ClaimType
from app.retrieval.sufficiency import EvidenceDesignFact, QuestionCategory, design_eligible
from app.validation.models import (
    ConclusionJustificationStatus,
    FrozenModel,
    NumericAlignment,
    ValidationIssue,
)
from app.validation.relations import ClaimRelation, ClaimRelationAssessment, ClaimScope, Materiality

VERSION = "conclusion-qualifier-1.0"
# Exactly the existing policy-1.3 causal design gate, not a new source hierarchy.
CAUSAL_DESIGNS = frozenset({
    "randomized_controlled_trial", "clinical_trial", "systematic_review", "meta_analysis",
})
CAUSAL_TYPES = frozenset({ClaimType.CAUSAL, ClaimType.PREVENTION, ClaimType.TREATMENT})


class QualificationReason(StrEnum):
    MATERIAL_SUPPORT = "MATERIAL_SUPPORT"
    MATERIAL_CONTRADICTION = "MATERIAL_CONTRADICTION"
    CONFLICTING_FINDINGS = "CONFLICTING_FINDINGS"
    ONLY_INSUFFICIENT_OR_CONTEXT = "ONLY_INSUFFICIENT_OR_CONTEXT"
    ONE_SIDED_DECISIVE_FINDINGS = "ONE_SIDED_DECISIVE_FINDINGS"
    NO_MATERIAL_PROPOSED_DIRECTION = "NO_MATERIAL_PROPOSED_DIRECTION"
    CAUSAL_DESIGN_INSUFFICIENT = "CAUSAL_DESIGN_INSUFFICIENT"
    MATERIAL_RELATION_UNCERTAIN = "MATERIAL_RELATION_UNCERTAIN"
    INCOMPATIBLE_SCOPE = "INCOMPATIBLE_SCOPE"
    REQUIRED_FINDING_UNAVAILABLE = "REQUIRED_FINDING_UNAVAILABLE"
    UNRESOLVED_REQUIRED_QUANTITY = "UNRESOLVED_REQUIRED_QUANTITY"
    FATAL_EVIDENCE_DEFECT = "FATAL_EVIDENCE_DEFECT"
    RELATION_SET_INVALID = "RELATION_SET_INVALID"
    RISK_CLASS_INVALID = "RISK_CLASS_INVALID"
    MATERIAL_MAGNITUDE_NOT_SUPPORTED = "MATERIAL_MAGNITUDE_NOT_SUPPORTED"
    INTEGRITY_NOT_ESTABLISHED = "INTEGRITY_NOT_ESTABLISHED"


class FindingQualificationInput(FrozenModel):
    statement_id: str
    study_designs: tuple[str, ...]
    deterministic_scopes: tuple[str, ...] = ()
    deterministic_relations: tuple[str, ...] = ()
    claim_magnitude_alignment: NumericAlignment = NumericAlignment.NOT_APPLICABLE
    integrity_statuses: tuple[str, ...] = ()
    evidence_design_facts: tuple[EvidenceDesignFact, ...] = ()


class ConclusionQualifierInput(FrozenModel):
    proposed_label: JudgeLabel | None
    claim_type: ClaimType | None
    risk_class: str
    findings: tuple[FindingQualificationInput, ...]
    relations: tuple[ClaimRelationAssessment, ...]
    based_on_statement_ids: tuple[str, ...]
    defects: tuple[ValidationIssue, ...] = ()
    required_findings_available: bool = True
    evidence_policy: Literal["legacy-1.0", "question-evidence-1.0", "question-evidence-2.0",
                                "question-evidence-2.1"] \
        = "legacy-1.0"
    question_category: QuestionCategory = "other"


class ConclusionQualification(FrozenModel):
    status: ConclusionJustificationStatus
    decisive_statement_ids: tuple[str, ...] = ()
    conflicting_statement_ids: tuple[str, ...] = ()
    insufficient_statement_ids: tuple[str, ...] = ()
    contextual_statement_ids: tuple[str, ...] = ()
    reason_codes: tuple[QualificationReason, ...]


class ConclusionQualificationAudit(FrozenModel):
    version: str = VERSION
    input: ConclusionQualifierInput
    output: ConclusionQualification


def qualify_conclusion(data: ConclusionQualifierInput) -> ConclusionQualification:
    """No medical label substitution, model call, clock, network or randomness."""
    finding_ids = tuple(item.statement_id for item in data.findings)
    relation_ids = tuple(item.statement_id for item in data.relations)
    dependencies = set(data.based_on_statement_ids)

    def early(status: ConclusionJustificationStatus, reason: QualificationReason
              ) -> ConclusionQualification:
        return ConclusionQualification(status=status, reason_codes=(reason,))

    if data.risk_class not in {"standard", "high"}:
        return early(ConclusionJustificationStatus.NOT_JUSTIFIED,
                     QualificationReason.RISK_CLASS_INVALID)
    if any(issue.severity == "fatal" for issue in data.defects):
        return early(ConclusionJustificationStatus.NOT_JUSTIFIED,
                     QualificationReason.FATAL_EVIDENCE_DEFECT)
    if not data.required_findings_available:
        return early(ConclusionJustificationStatus.UNCERTAIN,
                     QualificationReason.REQUIRED_FINDING_UNAVAILABLE)
    if any(issue.issue_code == "NUMERIC_UNCERTAIN" and (
        issue.target_id in dependencies or issue.target_id == "conclusion"
    ) for issue in data.defects):
        return early(ConclusionJustificationStatus.UNCERTAIN,
                     QualificationReason.UNRESOLVED_REQUIRED_QUANTITY)
    if (not finding_ids or finding_ids != relation_ids or len(set(finding_ids)) != len(finding_ids)
            or not dependencies or not dependencies <= set(finding_ids)):
        return early(ConclusionJustificationStatus.UNCERTAIN,
                     QualificationReason.RELATION_SET_INVALID)

    by_id = {f.statement_id: f for f in data.findings}
    if any(status in {"retracted", "unknown", "expression_of_concern"}
           for finding in data.findings for status in finding.integrity_statuses):
        return early(ConclusionJustificationStatus.UNCERTAIN,
                     QualificationReason.INTEGRITY_NOT_ESTABLISHED)
    supporting: list[str] = []
    contradicting: list[str] = []
    insufficient: list[str] = []
    contextual: list[str] = []
    uncertain: list[str] = []
    magnitude_blocked: list[str] = []
    for item in data.relations:
        finding = by_id[item.statement_id]
        if (data.evidence_policy in {"question-evidence-1.0", "question-evidence-2.0",
                                "question-evidence-2.1"}
                and finding.evidence_design_facts
                and not any(f.role == "direct" for f in finding.evidence_design_facts)):
            contextual.append(item.statement_id)
            continue
        if (item.relation == ClaimRelation.CONTEXT_ONLY
                or item.materiality == Materiality.CONTEXTUAL):
            contextual.append(item.statement_id)
            continue
        if (item.relation == ClaimRelation.UNCERTAIN
                or item.materiality == Materiality.UNCERTAIN
                or item.scope == ClaimScope.UNCERTAIN):
            uncertain.append(item.statement_id)
            continue
        if (item.relation == ClaimRelation.INSUFFICIENT
                or item.scope not in {ClaimScope.ALIGNED, ClaimScope.NARROWER}
                or "mismatch" in by_id[item.statement_id].deterministic_scopes
                or "reverse" in by_id[item.statement_id].deterministic_relations):
            insufficient.append(item.statement_id)
            continue
        if (data.claim_type in CAUSAL_TYPES and finding.deterministic_relations
                and set(finding.deterministic_relations) == {"weaker_than_claim"}):
            insufficient.append(item.statement_id)
            continue
        # Accurate counterestimates need not equal the user's number. This guard
        # blocks promotion to SUPPORT only; it never manufactures a contrary vote.
        if (item.relation == ClaimRelation.SUPPORTS and finding.claim_magnitude_alignment
                in {NumericAlignment.MISMATCH, NumericAlignment.UNCERTAIN}):
            magnitude_blocked.append(item.statement_id)
            insufficient.append(item.statement_id)
            continue
        if item.relation == ClaimRelation.SUPPORTS:
            supporting.append(item.statement_id)
        elif item.relation == ClaimRelation.CONTRADICTS:
            contradicting.append(item.statement_id)

    def decisive(ids: list[str]) -> list[str]:
        return [identifier for identifier in ids if identifier in dependencies
                and next(r for r in data.relations if r.statement_id == identifier).materiality
                == Materiality.DECISIVE]

    support_decisive, against_decisive = decisive(supporting), decisive(contradicting)
    causal = data.claim_type in CAUSAL_TYPES

    def design_sufficient(ids: list[str]) -> bool:
        if data.evidence_policy in {"question-evidence-1.0", "question-evidence-2.0",
                                "question-evidence-2.1"}:
            peers = tuple(f for identifier in ids
                          for f in by_id[identifier].evidence_design_facts)
            return any(design_eligible(data.question_category, fact,
                                      policy=data.evidence_policy, peers=peers)
                       for identifier in ids
                       for fact in by_id[identifier].evidence_design_facts)
        return not causal or any(
            set(by_id[identifier].study_designs) & CAUSAL_DESIGNS for identifier in ids
        )

    sufficient_support = bool(support_decisive) and design_sufficient(support_decisive)
    sufficient_against = bool(against_decisive) and design_sufficient(against_decisive)
    conflict = bool(supporting and contradicting)
    selected: tuple[str, ...] = ()
    codes: tuple[QualificationReason, ...]
    status = ConclusionJustificationStatus.NOT_JUSTIFIED
    if data.proposed_label == JudgeLabel.NOT_ENOUGH_EVIDENCE:
        if conflict:
            status, codes = (ConclusionJustificationStatus.JUSTIFIED,
                             (QualificationReason.CONFLICTING_FINDINGS,))
        elif (sufficient_support or sufficient_against) and not uncertain:
            codes = (QualificationReason.ONE_SIDED_DECISIVE_FINDINGS,)
        else:
            status = ConclusionJustificationStatus.JUSTIFIED
            codes = ((QualificationReason.CAUSAL_DESIGN_INSUFFICIENT,)
                     if causal and (supporting or contradicting) else
                     (QualificationReason.ONLY_INSUFFICIENT_OR_CONTEXT,))
    elif uncertain:
        status, codes = (ConclusionJustificationStatus.UNCERTAIN,
                         (QualificationReason.MATERIAL_RELATION_UNCERTAIN,))
    elif conflict:
        codes = (QualificationReason.CONFLICTING_FINDINGS,)
    else:
        ids = supporting if data.proposed_label == JudgeLabel.SUPPORTED else contradicting
        material_dependencies = [identifier for identifier in ids if identifier in dependencies]
        decisive_ids = decisive(ids)
        if not material_dependencies or not decisive_ids:
            codes = (QualificationReason.MATERIAL_MAGNITUDE_NOT_SUPPORTED
                     if data.proposed_label == JudgeLabel.SUPPORTED and magnitude_blocked
                     else QualificationReason.NO_MATERIAL_PROPOSED_DIRECTION,)
        elif not design_sufficient(decisive_ids):
            codes = (QualificationReason.CAUSAL_DESIGN_INSUFFICIENT,)
        else:
            status = ConclusionJustificationStatus.JUSTIFIED
            selected = tuple(decisive_ids)
            codes = (QualificationReason.MATERIAL_SUPPORT if data.proposed_label ==
                     JudgeLabel.SUPPORTED else QualificationReason.MATERIAL_CONTRADICTION,)
    return ConclusionQualification(
        status=status, decisive_statement_ids=selected,
        conflicting_statement_ids=tuple(supporting + contradicting) if conflict else (),
        insufficient_statement_ids=tuple(insufficient), contextual_statement_ids=tuple(contextual),
        reason_codes=codes,
    )
