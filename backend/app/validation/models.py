"""Typed per-citation and per-judge validation audit contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.judging.models import JudgeLabel
from app.retrieval.models import IntegrityStatus


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NumericAlignment(StrEnum):
    ALIGNED = "aligned"
    MISMATCH = "mismatch"
    NOT_APPLICABLE = "not_applicable"
    UNCERTAIN = "uncertain"


class ScopeAlignment(StrEnum):
    ALIGNED = "aligned"
    PARTIAL = "partial"
    MISMATCH = "mismatch"
    UNCERTAIN = "uncertain"


class RelationAlignment(StrEnum):
    ALIGNED = "aligned"
    WEAKER_THAN_CLAIM = "weaker_than_claim"
    REVERSE = "reverse"
    MISMATCH = "mismatch"
    UNCERTAIN = "uncertain"


class EntailmentStatus(StrEnum):
    ENTAILS_JUDGE_USE = "entails_judge_use"
    CONTRADICTS_JUDGE_USE = "contradicts_judge_use"
    INSUFFICIENT_FOR_JUDGE_USE = "insufficient_for_judge_use"
    UNCERTAIN = "uncertain"


class ValidationStatus(StrEnum):
    VALIDATED = "validated"
    PARTIALLY_VALIDATED = "partially_validated"
    INVALID = "invalid"
    UNABLE_TO_VALIDATE = "unable_to_validate"


class IssueCode(StrEnum):
    CITATION_NOT_IN_PACK = "CITATION_NOT_IN_PACK"
    CITATION_NOT_SELECTED = "CITATION_NOT_SELECTED"
    PACK_HASH_MISMATCH = "PACK_HASH_MISMATCH"
    PASSAGE_HASH_MISMATCH = "PASSAGE_HASH_MISMATCH"
    DOCUMENT_PROVENANCE_MISSING = "DOCUMENT_PROVENANCE_MISSING"
    RETRACTED_CITATION = "RETRACTED_CITATION"
    MATERIAL_NUMERIC_MISMATCH = "MATERIAL_NUMERIC_MISMATCH"
    MATERIAL_SCOPE_MISMATCH = "MATERIAL_SCOPE_MISMATCH"
    RELATION_STRENGTH_MISMATCH = "RELATION_STRENGTH_MISMATCH"
    EVIDENCE_CONTRADICTS_JUDGE_USE = "EVIDENCE_CONTRADICTS_JUDGE_USE"
    NO_VALID_DECISIVE_CITATION = "NO_VALID_DECISIVE_CITATION"
    INTEGRITY_UNKNOWN = "INTEGRITY_UNKNOWN"
    EXPRESSION_OF_CONCERN = "EXPRESSION_OF_CONCERN"
    PARTIAL_SCOPE_MATCH = "PARTIAL_SCOPE_MATCH"
    NUMERIC_UNCERTAIN = "NUMERIC_UNCERTAIN"
    RELATION_UNCERTAIN = "RELATION_UNCERTAIN"
    ENTAILMENT_UNCERTAIN = "ENTAILMENT_UNCERTAIN"
    ENTAILMENT_UNAVAILABLE = "ENTAILMENT_UNAVAILABLE"
    QUALITY_PRIOR_LOW = "QUALITY_PRIOR_LOW"


FATAL_ISSUES = frozenset({
    IssueCode.CITATION_NOT_IN_PACK, IssueCode.CITATION_NOT_SELECTED,
    IssueCode.PACK_HASH_MISMATCH, IssueCode.PASSAGE_HASH_MISMATCH,
    IssueCode.DOCUMENT_PROVENANCE_MISSING, IssueCode.RETRACTED_CITATION,
    IssueCode.MATERIAL_NUMERIC_MISMATCH, IssueCode.MATERIAL_SCOPE_MISMATCH,
    IssueCode.RELATION_STRENGTH_MISMATCH,
    IssueCode.EVIDENCE_CONTRADICTS_JUDGE_USE,
    IssueCode.NO_VALID_DECISIVE_CITATION,
})


class EntailmentInput(FrozenModel):
    evidence_id: str
    role: Literal["cited", "opposing"]
    exact_claim: str
    judge_label: JudgeLabel
    reasoning_summary: str
    passage: str
    document_title: str
    document_pmid: str
    study_design: str


class EntailmentOutput(FrozenModel):
    status: EntailmentStatus
    evidence_claim: str = Field(min_length=1, max_length=600)
    scope_match: ScopeAlignment
    reason: str = Field(min_length=1, max_length=600)
    evidence_id: str


class CitationValidation(FrozenModel):
    evidence_id: str
    role: Literal["cited", "opposing"]
    exists: bool
    selected_for_judging: bool
    passage_hash_matches: bool
    document_provenance_exists: bool
    integrity_status: IntegrityStatus | None
    numeric_alignment: NumericAlignment
    scope_alignment: ScopeAlignment
    relation_alignment: RelationAlignment
    entailment_status: EntailmentStatus
    entailment_scope_match: ScopeAlignment | None = None
    evidence_claim: str | None = None
    entailment_reason: str | None = None
    issue_codes: tuple[IssueCode, ...] = ()
    warnings: tuple[IssueCode, ...] = ()
    validator_provenance: dict[str, str] = Field(default_factory=dict)


class JudgeValidationResult(FrozenModel):
    judge_run_id: UUID
    evidence_pack_id: UUID
    evidence_pack_hash: str
    judge_label: JudgeLabel
    citation_validations: tuple[CitationValidation, ...]
    opposing_citation_validations: tuple[CitationValidation, ...]
    validation_status: ValidationStatus
    fatal_issue_codes: tuple[IssueCode, ...]
    warnings: tuple[IssueCode, ...]
    validation_version: str


class JudgeValidationRun(FrozenModel):
    id: UUID
    judge_run_id: UUID
    evidence_pack_id: UUID
    evidence_pack_hash: str
    validation_version: str
    deterministic_validator_version: str
    entailment_provider: str | None
    entailment_model: str | None
    prompt_version: str | None
    prompt_hash: str | None
    started_at: datetime
    completed_at: datetime
    status: ValidationStatus
    result: JudgeValidationResult
    error_category: str | None
    latency_ms: int = Field(ge=0)
    attempt_count: int = Field(ge=0)
