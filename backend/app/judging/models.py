"""Strict per-judge contracts and append-only run summaries."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class JudgeLabel(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    NOT_ENOUGH_EVIDENCE = "not_enough_evidence"


class EvidenceSufficiency(StrEnum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"


class UncertaintyReason(StrEnum):
    ASSOCIATION_NOT_CAUSATION = "association_not_causation"
    INDIRECT_EVIDENCE = "indirect_evidence"
    POPULATION_MISMATCH = "population_mismatch"
    EXPOSURE_MISMATCH = "exposure_mismatch"
    COMPARATOR_MISMATCH = "comparator_mismatch"
    OUTCOME_MISMATCH = "outcome_mismatch"
    TIMEFRAME_MISMATCH = "timeframe_mismatch"
    NUMERIC_MISMATCH = "numeric_mismatch"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    LIMITED_EVIDENCE = "limited_evidence"
    INTEGRITY_UNCERTAIN = "integrity_uncertain"
    OTHER = "other"


class JudgeDecision(BaseModel):
    """A model judgment, not the Lens of Truth verdict or confidence."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: str = Field(pattern=r"^1\.0$")
    label: JudgeLabel
    cited_evidence_ids: tuple[str, ...]
    opposing_evidence_ids: tuple[str, ...]
    reasoning_summary: str = Field(min_length=1, max_length=1200)
    claim_strength_assessed: str = Field(min_length=1, max_length=300)
    evidence_sufficiency: EvidenceSufficiency
    uncertainty_reasons: tuple[UncertaintyReason, ...]

    @field_validator("cited_evidence_ids", "opposing_evidence_ids")
    @classmethod
    def no_duplicate_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate evidence IDs")
        return value

    @model_validator(mode="after")
    def no_overlap(self) -> "JudgeDecision":
        if set(self.cited_evidence_ids) & set(self.opposing_evidence_ids):
            raise ValueError("evidence ID cannot be cited and opposing")
        if self.label == JudgeLabel.NOT_ENOUGH_EVIDENCE:
            if self.evidence_sufficiency != EvidenceSufficiency.INSUFFICIENT:
                raise ValueError("inconclusive judgment requires insufficient evidence")
        elif (
            self.evidence_sufficiency != EvidenceSufficiency.SUFFICIENT
            or not self.cited_evidence_ids
        ):
            raise ValueError("decisive judgment requires sufficient cited evidence")
        return self


class JudgeSlot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: int = Field(ge=1, le=3)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    api_key: str | None = None
    search_override_active: bool = False
    search_guard_bypassed: bool = False


class ProviderResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_request_id: str | None = None
    model_snapshot: str | None = None


class JudgeRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    judge_run_id: UUID
    claim_id: UUID
    evidence_pack_id: UUID
    evidence_pack_hash: str
    slot: int
    provider: str
    model: str
    model_family: str
    model_snapshot: str | None = None
    search_override_active: bool = False
    search_guard_bypassed: bool = False
    search_isolation_verified: bool = False
    prompt_version: str
    prompt_hash: str
    requested_at: datetime
    responded_at: datetime
    latency_ms: int = Field(ge=0)
    attempt_count: int = Field(ge=0, le=2)
    outcome_status: str
    response_json: dict[str, object] | None = None
    decision: JudgeDecision | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_request_id: str | None = None
    error_category: str | None = None

    @model_validator(mode="after")
    def valid_search_audit(self) -> "JudgeRun":
        if self.search_guard_bypassed and (
            not self.search_override_active or self.search_isolation_verified
        ):
            raise ValueError("bypassed search guard cannot claim verified isolation")
        return self


class DisagreementSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    successful_judges: int
    total_judges: int
    label_counts: dict[JudgeLabel, int]
    unanimous: bool | None
    pairwise_agreement: float | None


def describe_disagreement(runs: tuple[JudgeRun, ...]) -> DisagreementSummary:
    """Describe observed labels only; never aggregate a medical verdict."""

    counts = {label: 0 for label in JudgeLabel}
    labels = [run.decision.label for run in runs if run.decision is not None]
    for label in labels:
        counts[label] += 1
    pairs = [(left, right) for index, left in enumerate(labels)
             for right in labels[index + 1:]]
    return DisagreementSummary(
        successful_judges=len(labels), total_judges=len(runs), label_counts=counts,
        unanimous=len(set(labels)) == 1 if len(labels) >= 2 else None,
        pairwise_agreement=(sum(a == b for a, b in pairs) / len(pairs)) if pairs else None,
    )
