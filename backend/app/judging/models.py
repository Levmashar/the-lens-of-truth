"""Strict per-judge contracts and append-only run summaries."""

import json
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)


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
    """Historical v1 free-text decision; never infer statement mappings from it."""

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


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    evidence_id: str = Field(pattern=r"^E[1-9][0-9]*$")
    quote: str = Field(min_length=3, max_length=32000)


class JudgeStatement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    statement_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    text: str = Field(min_length=5, max_length=600)
    kind: Literal["study_finding", "study_method", "limitation"]
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=4)
    source_unit_ids: tuple[str, ...] = ()
    qualitative_finding: str | None = Field(default=None, min_length=5, max_length=600)
    numeric_details: tuple[str, ...] = Field(default=(), max_length=4)
    numeric_dependency: bool | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_shape(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        result = handler(self)
        if not self.source_unit_ids:
            result.pop("source_unit_ids", None)
        if self.qualitative_finding is None:
            for key in ("qualitative_finding", "numeric_details", "numeric_dependency"):
                result.pop(key, None)
        return dict(result)

    @model_validator(mode="after")
    def distinct_refs(self) -> "JudgeStatement":
        ids = [ref.evidence_id for ref in self.evidence_refs]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate statement evidence reference")
        return self


class JudgeConclusion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    based_on_statement_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    justification: str = Field(min_length=5, max_length=1200)
    qualitative_justification: str | None = Field(default=None, min_length=5, max_length=1200)
    numeric_dependency: bool | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_shape(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        result = dict(handler(self))
        if self.qualitative_justification is None:
            result.pop("qualitative_justification", None)
            result.pop("numeric_dependency", None)
        return result


class JudgeDecisionV2(BaseModel):
    """Source-attributed findings and a separate, proposed conclusion."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["2.0", "2.1", "2.2", "2.3"]
    label: JudgeLabel
    statements: tuple[JudgeStatement, ...] = Field(min_length=1, max_length=8)
    conclusion: JudgeConclusion
    uncertainty_reasons: tuple[UncertaintyReason, ...] = ()

    @model_validator(mode="after")
    def valid_references(self) -> "JudgeDecisionV2":
        ids = [statement.statement_id for statement in self.statements]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate statement ID")
        used = self.conclusion.based_on_statement_ids
        if len(used) != len(set(used)) or not set(used) <= set(ids):
            raise ValueError("conclusion references unknown or duplicate statement")
        if self.schema_version in {"2.1", "2.2", "2.3"} and any(
            not s.source_unit_ids for s in self.statements
        ):
            raise ValueError("Backend source units required for unit decisions")
        if self.schema_version == "2.3":
            if len(self.statements) > 5 or any(
                s.qualitative_finding is None or s.numeric_dependency is None
                or any(not detail or len(detail) > 600 for detail in s.numeric_details)
                for s in self.statements
            ) or self.conclusion.qualitative_justification is None or (
                self.conclusion.numeric_dependency is None
            ):
                raise ValueError("2.3 requires separate qualitative propositions and dependencies")
        elif any(s.qualitative_finding is not None or s.numeric_details
                 or s.numeric_dependency is not None for s in self.statements) or (
                     self.conclusion.qualitative_justification is not None
                     or self.conclusion.numeric_dependency is not None
                 ):
            raise ValueError("Historical contracts cannot carry 2.3 semantic fields")
        if self.schema_version == "2.0" and any(
            len(ref.quote) > 1200 or statement.source_unit_ids
            for statement in self.statements for ref in statement.evidence_refs
        ):
            raise ValueError("Historical free-text citation contract unchanged")
        return self


AnyJudgeDecision = JudgeDecision | JudgeDecisionV2


def decision_evidence_ids(decision: AnyJudgeDecision) -> tuple[str, ...]:
    if isinstance(decision, JudgeDecisionV2):
        return tuple(dict.fromkeys(
            ref.evidence_id for statement in decision.statements
            for ref in statement.evidence_refs
        ))
    return tuple(dict.fromkeys((*decision.cited_evidence_ids, *decision.opposing_evidence_ids)))


def parse_stored_decision(data: dict[str, object]) -> AnyJudgeDecision:
    # Strict models accept JSON arrays/enums through the JSON parser, while
    # model_validate(dict) correctly rejects Python lists and raw enum strings.
    # JSONB is decoded to a dict by SQLAlchemy, so restore JSON parsing here.
    encoded = json.dumps(data)
    if data.get("schema_version") in {"2.0", "2.1", "2.2", "2.3"}:
        return JudgeDecisionV2.model_validate_json(encoded)
    return JudgeDecision.model_validate_json(encoded)


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
    request_json_schema: bool = True


class ProviderResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str
    system_fingerprint: str | None = None
    response_id: str | None = None
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
    schema_version_inferred: bool = False
    model_identity_verified: bool = False
    model_family_verified: bool = False
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
    decision: AnyJudgeDecision | None = None
    input_snapshot_version: str | None = None
    input_snapshot_hash: str | None = None
    input_snapshot_json: dict[str, object] | None = None
    revision_of_judge_run_id: UUID | None = None
    semantic_revision_number: int = Field(default=0, ge=0, le=1)
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
        if self.schema_version_inferred and self.decision is None:
            raise ValueError("schema version inference requires a valid decision")
        if (self.revision_of_judge_run_id is None) != (self.semantic_revision_number == 0):
            raise ValueError("semantic revision number and parent must agree")
        if isinstance(self.decision, JudgeDecisionV2) and (
            self.input_snapshot_version != f"judge-input-{self.decision.schema_version}"
            or not self.input_snapshot_hash or self.input_snapshot_json is None
        ):
            raise ValueError("V2 decision requires a frozen judge-visible input snapshot")
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
