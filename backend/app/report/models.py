"""Typed, immutable Phase 6C report contract."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.judging.models import JudgeLabel
from app.pipeline.claim_types import ClaimType
from app.retrieval.models import IntegrityStatus, StudyDesign
from app.verdict.models import LensVerdict, ReasonCode


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EvidenceRole(StrEnum):
    SUPPORTING = "supporting"
    OPPOSING = "opposing"
    RELEVANT_BUT_INSUFFICIENT = "relevant_but_insufficient"


class EvidenceState(StrEnum):
    VALIDATED_SUPPORT = "validated_support"
    VALIDATED_CONTRADICTION = "validated_contradiction"
    CONFLICTING = "conflicting"
    RELEVANT_BUT_INSUFFICIENT = "relevant_but_insufficient"
    NO_RESULTS = "no_results"
    VERIFICATION_INCOMPLETE = "verification_incomplete"


class ReportClaim(FrozenModel):
    text: str
    claim_type: ClaimType | None


class ReportReason(FrozenModel):
    code: ReasonCode
    text: str


class SourceExcerpt(FrozenModel):
    evidence_id: str
    source_unit_id: str
    section: str
    exact_text: str
    truncated: bool
    passage_sha256: str


class SourceCard(FrozenModel):
    evidence_id: str
    pmid: str | None
    doi: str | None
    title: str
    journal: str | None
    publication_date: str | None
    study_design: StudyDesign
    integrity_status: IntegrityStatus
    evidence_roles: tuple[EvidenceRole, ...]
    exact_excerpt: str
    excerpt_truncated: bool
    passage_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    passage_section: str
    source_url: str
    citation_validated: bool
    cited_by_judge_run_ids: tuple[UUID, ...]
    cited_by_validation_run_ids: tuple[UUID, ...]
    limitations: tuple[str, ...] = ()
    document_id: str | None = None
    source_kind: str = "pubmed"
    organization: str | None = None
    document_purpose: str | None = None
    analysis_design: str | None = None
    exposure_assignment: str | None = None
    attribution: str | None = None
    currency: str | None = None
    excerpts: tuple[SourceExcerpt, ...] = ()


class SourceReference(FrozenModel):
    evidence_id: str
    pmid: str | None
    doi: str | None
    url: str


class NeutralRetrievedSource(FrozenModel):
    """Frozen source excerpt, explicitly not validated support/opposition."""

    evidence_id: str
    pmid: str | None
    doi: str | None
    title: str
    publication_date: str | None
    passage_section: str
    exact_excerpt: str
    excerpt_truncated: bool
    passage_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_url: str


class ExcludedAssessment(FrozenModel):
    judge_run_id: UUID
    slot: int
    reasons: tuple[ReportReason, ...]


class ReportJudgeSummary(FrozenModel):
    qualified: int = Field(ge=0)
    excluded: int = Field(ge=0)
    validated_label_counts: dict[JudgeLabel, int]
    description: str
    excluded_assessments: tuple[ExcludedAssessment, ...]


class ReportVerificationStatus(FrozenModel):
    evidence_state: EvidenceState
    validated_citations_shown: int = Field(ge=0)
    production_qualified: bool
    development_notice: str | None


class ReportProvenance(FrozenModel):
    report_version: str
    verdict_run_id: UUID
    verdict_policy_version: str
    verdict_semantic_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_pack_id: UUID
    evidence_pack_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_pack_version: str
    judge_run_ids: tuple[UUID, ...]
    judge_validation_run_ids: tuple[UUID, ...]
    report_builder_version: str
    generated_at: datetime
    production_qualified: bool


class ExplanationReason(StrEnum):
    NUMERIC_MAGNITUDE_UNVERIFIED = "numeric_magnitude_unverified"
    NUMERIC_EVIDENCE_NOT_COMPARABLE = "numeric_evidence_not_comparable"
    SCOPE_TOO_NARROW = "scope_too_narrow"
    COMPARATOR_MISMATCH = "comparator_mismatch"
    POPULATION_MISMATCH = "population_mismatch"
    OUTCOME_MISMATCH = "outcome_mismatch"
    CAUSAL_DESIGN_INSUFFICIENT = "causal_design_insufficient"
    CONFLICTING_MATERIAL_EVIDENCE = "conflicting_material_evidence"
    ONLY_INDIRECT_EVIDENCE = "only_indirect_evidence"
    ONLY_CONTEXTUAL_EVIDENCE = "only_contextual_evidence"
    INSUFFICIENT_DIRECT_EVIDENCE = "insufficient_direct_evidence"
    TECHNICAL_VALIDATION_FAILURE = "technical_validation_failure"
    INSUFFICIENT_QUALIFIED_JUDGES = "insufficient_qualified_judges"
    SUPPORTED_BY_VALIDATED_EVIDENCE = "supported_by_validated_evidence"
    CONTRADICTED_BY_VALIDATED_EVIDENCE = "contradicted_by_validated_evidence"
    OTHER_BOUNDED_REASON = "other_bounded_reason"


class VerdictExplanation(FrozenModel):
    version: Literal["1.0"] = "1.0"
    summary: str = Field(min_length=1)
    reason_category: ExplanationReason
    established: str | None
    unresolved: str | None
    evidence_ids: tuple[str, ...]


class LensReport(FrozenModel):
    report_version: str
    verdict_run_id: UUID
    claim: ReportClaim
    verdict: LensVerdict
    verdict_display: str
    headline: str
    short_summary: str
    verdict_explanation: VerdictExplanation | None = Field(
        default=None, exclude_if=lambda value: value is None,
    )
    why_this_result: tuple[ReportReason, ...]
    key_evidence: tuple[SourceCard, ...]
    neutral_retrieved_sources: tuple[NeutralRetrievedSource, ...] = ()
    evidence_limitations: tuple[str, ...]
    judge_summary: ReportJudgeSummary
    verification_status: ReportVerificationStatus
    sources: tuple[SourceReference, ...]
    safety_notice: str
    production_qualified: bool
    provenance: ReportProvenance
    semantic_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def visible_qualification(self) -> "LensReport":
        if self.report_version == "1.3":
            if self.verdict_explanation is None:
                raise ValueError("Report 1.3 requires a saved verdict explanation")
            if self.short_summary != self.verdict_explanation.summary:
                raise ValueError("Report summary differs from saved verdict explanation")
        elif self.verdict_explanation is not None:
            raise ValueError("Historical report cannot carry a new verdict explanation")
        if (self.production_qualified != self.verification_status.production_qualified
                or self.production_qualified != self.provenance.production_qualified):
            raise ValueError("Report production qualification mismatch")
        if not self.production_qualified and not self.verification_status.development_notice:
            raise ValueError("Non-production report must display a development notice")
        if self.production_qualified and self.verification_status.development_notice:
            raise ValueError("Production report cannot carry a development notice")
        return self
