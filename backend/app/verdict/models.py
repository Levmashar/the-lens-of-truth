"""Immutable, explicit provenance and result contracts for Phase 6B."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.judging.models import JudgeLabel, JudgeRun
from app.retrieval.models import EvidencePack
from app.validation.models import JudgeValidationRun, ValidationStatus


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AggregationMode(StrEnum):
    PRODUCTION = "production"
    FIXTURE_OR_EVALUATION = "fixture_or_evaluation"


class LensVerdict(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    NOT_ENOUGH_EVIDENCE = "not_enough_evidence"
    UNABLE_TO_VERIFY_RELIABLY = "unable_to_verify_reliably"


class ReasonCode(StrEnum):
    SUPPORTED_BY_MULTIPLE_VALIDATED_JUDGES = "SUPPORTED_BY_MULTIPLE_VALIDATED_JUDGES"
    CONTRADICTED_BY_MULTIPLE_VALIDATED_JUDGES = "CONTRADICTED_BY_MULTIPLE_VALIDATED_JUDGES"
    UNANIMOUS_HIGH_RISK_SUPPORT = "UNANIMOUS_HIGH_RISK_SUPPORT"
    UNANIMOUS_HIGH_RISK_CONTRADICTION = "UNANIMOUS_HIGH_RISK_CONTRADICTION"
    VALIDATED_JUDGE_DISAGREEMENT = "VALIDATED_JUDGE_DISAGREEMENT"
    INSUFFICIENT_DECISIVE_EVIDENCE = "INSUFFICIENT_DECISIVE_EVIDENCE"
    ALL_JUDGES_NOT_ENOUGH_EVIDENCE = "ALL_JUDGES_NOT_ENOUGH_EVIDENCE"
    RETRIEVAL_NO_RESULTS = "RETRIEVAL_NO_RESULTS"
    RETRIEVAL_TECHNICAL_FAILURE = "RETRIEVAL_TECHNICAL_FAILURE"
    PACK_HASH_MISMATCH = "PACK_HASH_MISMATCH"
    PACK_UNAVAILABLE = "PACK_UNAVAILABLE"
    PACK_VERSION_UNSUPPORTED = "PACK_VERSION_UNSUPPORTED"
    PACK_SELECTION_INVALID = "PACK_SELECTION_INVALID"
    CLAIM_UNAVAILABLE = "CLAIM_UNAVAILABLE"
    NORMALIZATION_INCOMPLETE = "NORMALIZATION_INCOMPLETE"
    RISK_CLASS_INVALID = "RISK_CLASS_INVALID"
    AUDIT_RECORD_MISSING = "AUDIT_RECORD_MISSING"
    AUDIT_RECORD_MISMATCH = "AUDIT_RECORD_MISMATCH"
    AUDIT_RECORD_INVALID = "AUDIT_RECORD_INVALID"
    INSUFFICIENT_QUALIFIED_JUDGES = "INSUFFICIENT_QUALIFIED_JUDGES"
    INSUFFICIENT_VALIDATED_JUDGES = "INSUFFICIENT_VALIDATED_JUDGES"
    SEARCH_ISOLATION_UNVERIFIED = "SEARCH_ISOLATION_UNVERIFIED"
    SEARCH_GUARD_BYPASSED = "SEARCH_GUARD_BYPASSED"
    MODEL_IDENTITY_UNVERIFIED = "MODEL_IDENTITY_UNVERIFIED"
    MODEL_FAMILY_UNVERIFIED = "MODEL_FAMILY_UNVERIFIED"
    DUPLICATE_MODEL_FAMILY = "DUPLICATE_MODEL_FAMILY"
    DUPLICATE_JUDGE_SLOT = "DUPLICATE_JUDGE_SLOT"
    JUDGE_FAILED = "JUDGE_FAILED"
    VALIDATION_UNAVAILABLE = "VALIDATION_UNAVAILABLE"
    VALIDATION_PROVIDER_UNAPPROVED = "VALIDATION_PROVIDER_UNAPPROVED"
    VALIDATION_PARTIAL = "VALIDATION_PARTIAL"
    VALIDATION_INVALID = "VALIDATION_INVALID"
    VALIDATION_FATAL_ISSUE = "VALIDATION_FATAL_ISSUE"
    EVALUATION_ONLY = "EVALUATION_ONLY"


class AggregationInput(FrozenModel):
    claim_id: UUID
    evidence_pack_id: UUID
    evidence_pack_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    judge_run_ids: tuple[UUID, ...]
    judge_validation_run_ids: tuple[UUID, ...]
    mode: AggregationMode
    policy_version: str

    @model_validator(mode="after")
    def unique_explicit_ids(self) -> "AggregationInput":
        if len(set(self.judge_run_ids)) != len(self.judge_run_ids):
            raise ValueError("Duplicate judge run IDs")
        if len(set(self.judge_validation_run_ids)) != len(self.judge_validation_run_ids):
            raise ValueError("Duplicate validation run IDs")
        object.__setattr__(self, "judge_run_ids", tuple(sorted(self.judge_run_ids)))
        object.__setattr__(self, "judge_validation_run_ids",
                           tuple(sorted(self.judge_validation_run_ids)))
        return self


class ClaimFacts(FrozenModel):
    claim_id: UUID
    normalization_status: str
    risk_class: str


class AggregationContext(FrozenModel):
    claim: ClaimFacts | None
    pack: EvidencePack | None
    stored_pack_hash: str | None
    stored_pack_version: str | None = None
    stored_pack_claim_id: UUID | None = None
    retrieval_status: str | None
    judges: tuple[JudgeRun, ...] = ()
    validations: tuple[JudgeValidationRun, ...] = ()
    audit_records_valid: bool = True


class JudgeQualification(FrozenModel):
    judge_run_id: UUID
    slot: int
    model_family: str
    label: JudgeLabel | None
    validation_status: ValidationStatus | None
    qualified: bool
    exclusion_reasons: tuple[ReasonCode, ...] = ()


class VerdictResult(FrozenModel):
    verdict: LensVerdict
    policy_version: str
    claim_id: UUID
    evidence_pack_id: UUID
    evidence_pack_hash: str
    input_judge_run_ids: tuple[UUID, ...]
    input_validation_run_ids: tuple[UUID, ...]
    mode: AggregationMode
    risk_class: str | None
    judge_qualifications: tuple[JudgeQualification, ...]
    qualified_judges: int
    excluded_judges: int
    validated_label_counts: dict[JudgeLabel, int]
    unanimous: bool | None
    conflicting_decisive_labels: bool
    disagreement_reason_codes: tuple[ReasonCode, ...]
    reason_codes: tuple[ReasonCode, ...]
    production_qualified: bool
    semantic_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
