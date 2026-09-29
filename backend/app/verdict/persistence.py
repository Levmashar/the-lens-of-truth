"""Read explicit audit IDs and append a new immutable verdict run."""

import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.judging.models import JudgeDecision, JudgeRun
from app.models.claim import Claim
from app.models.judge_run import JudgeRunRecord
from app.models.judge_validation_run import JudgeValidationRunRecord
from app.models.retrieval import EvidencePackRecord, RetrievalRun
from app.models.verdict_run import VerdictRunRecord
from app.pipeline.readiness import ready_for_evidence
from app.retrieval.models import EvidencePack
from app.validation.models import JudgeValidationResult, JudgeValidationRun, ValidationStatus
from app.verdict.models import (
    AggregationContext,
    AggregationInput,
    ClaimFacts,
    LensVerdict,
    ReasonCode,
    VerdictResult,
)
from app.verdict.service import semantic_result_hash

ENGINE_VERSION = "verdict-engine-1.1"


def _judge(row: JudgeRunRecord) -> JudgeRun:
    return JudgeRun(
        judge_run_id=row.id, claim_id=row.claim_id,
        evidence_pack_id=row.evidence_pack_id, evidence_pack_hash=row.evidence_pack_hash,
        slot=row.slot, provider=row.provider, model=row.model,
        model_family=row.model_family, model_snapshot=row.model_snapshot,
        schema_version_inferred=row.schema_version_inferred,
        model_identity_verified=row.model_identity_verified,
        model_family_verified=row.model_family_verified,
        search_override_active=row.search_override_active,
        search_guard_bypassed=row.search_guard_bypassed,
        search_isolation_verified=row.search_isolation_verified,
        prompt_version=row.prompt_version, prompt_hash=row.prompt_hash,
        requested_at=row.requested_at, responded_at=row.responded_at,
        latency_ms=row.latency_ms, attempt_count=row.attempt_count,
        outcome_status=row.outcome_status, response_json=row.response_json,
        decision=(JudgeDecision.model_validate_json(json.dumps(row.decision_json))
                  if row.decision_json is not None else None),
        input_tokens=row.input_tokens, output_tokens=row.output_tokens,
        provider_request_id=row.provider_request_id, error_category=row.error_category,
    )


def _validation(row: JudgeValidationRunRecord) -> JudgeValidationRun:
    return JudgeValidationRun(
        id=row.id, judge_run_id=row.judge_run_id,
        evidence_pack_id=row.evidence_pack_id, evidence_pack_hash=row.evidence_pack_hash,
        validation_version=row.validation_version,
        deterministic_validator_version=row.deterministic_validator_version,
        entailment_provider=row.entailment_provider,
        entailment_model=row.entailment_model, prompt_version=row.prompt_version,
        prompt_hash=row.prompt_hash, started_at=row.started_at,
        completed_at=row.completed_at, status=ValidationStatus(row.status),
        result=JudgeValidationResult.model_validate(row.result_json),
        error_category=row.error_category, latency_ms=row.latency_ms,
        attempt_count=row.attempt_count,
    )


def load_aggregation_context(
    session: Session, request: AggregationInput,
) -> AggregationContext:
    """Load only caller-named rows; missing/invalid records fail closed in policy."""

    claim = session.get(Claim, request.claim_id)
    claim_facts = (ClaimFacts(
        claim_id=claim.id, normalization_status=claim.normalization_status,
        risk_class=claim.risk_class,
        normalization_reviewed=ready_for_evidence(
            claim.normalization_status, pico_json=claim.pico_json,
            quality_json=claim.normalization_quality,
            standalone_status=claim.standalone_status,
            standalone_text=claim.normalized_text,
        ),
    ) if claim is not None else None)
    pack_row = session.get(EvidencePackRecord, request.evidence_pack_id)
    pack: EvidencePack | None = None
    retrieval_status: str | None = None
    audit_valid = True
    if pack_row is not None:
        try:
            pack = EvidencePack.model_validate(pack_row.snapshot_json)
        except (ValueError, TypeError):
            audit_valid = False
        retrieval = session.get(RetrievalRun, pack_row.run_id)
        retrieval_status = retrieval.status if retrieval is not None else None
        if retrieval is not None and retrieval.claim_id != request.claim_id:
            audit_valid = False
    judges: list[JudgeRun] = []
    validations: list[JudgeValidationRun] = []
    for judge_id in request.judge_run_ids:
        judge_row = session.get(JudgeRunRecord, judge_id)
        if judge_row is not None:
            try:
                judges.append(_judge(judge_row))
            except (ValueError, TypeError):
                audit_valid = False
    for validation_id in request.judge_validation_run_ids:
        validation_row = session.get(JudgeValidationRunRecord, validation_id)
        if validation_row is not None:
            try:
                validations.append(_validation(validation_row))
            except (ValueError, TypeError):
                audit_valid = False
    return AggregationContext(
        claim=claim_facts, pack=pack,
        stored_pack_hash=pack_row.snapshot_hash if pack_row else None,
        stored_pack_version=pack_row.version if pack_row else None,
        stored_pack_claim_id=pack_row.claim_id if pack_row else None,
        retrieval_status=retrieval_status, judges=tuple(judges),
        validations=tuple(validations), audit_records_valid=audit_valid,
    )


def persist_verdict_run(session: Session, result: VerdictResult) -> VerdictRunRecord:
    """Every execution inserts a distinct audit row; no UPDATE is ever issued."""

    pack = session.get(EvidencePackRecord, result.evidence_pack_id)
    if pack is None or pack.claim_id != result.claim_id:
        raise ValueError("Verdict run does not match a stored claim and Evidence Pack")
    if result.semantic_hash != semantic_result_hash(result):
        raise ValueError("Verdict result semantic hash mismatch")
    if (pack.snapshot_hash != result.evidence_pack_hash and not (
        result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
        and ReasonCode.PACK_HASH_MISMATCH in result.reason_codes
    )):
        raise ValueError("Pack hash mismatch must fail closed in the audit result")
    for judge_id in result.input_judge_run_ids:
        judge_row = session.get(JudgeRunRecord, judge_id)
        if judge_row is None or judge_row.evidence_pack_id != pack.id:
            raise ValueError("Verdict references a missing or foreign judge run")
    for validation_id in result.input_validation_run_ids:
        validation_row = session.get(JudgeValidationRunRecord, validation_id)
        if validation_row is None or validation_row.evidence_pack_id != pack.id:
            raise ValueError("Verdict references a missing or foreign validation run")
    record = VerdictRunRecord(
        claim_id=result.claim_id, evidence_pack_id=result.evidence_pack_id,
        evidence_pack_hash=result.evidence_pack_hash,
        judge_run_ids=[str(item) for item in result.input_judge_run_ids],
        judge_validation_run_ids=[str(item) for item in result.input_validation_run_ids],
        policy_version=result.policy_version, engine_version=ENGINE_VERSION,
        mode=result.mode.value, verdict=result.verdict.value,
        reason_codes=[item.value for item in result.reason_codes],
        result_json=result.model_dump(mode="json"),
        semantic_hash=result.semantic_hash,
        production_qualified=result.production_qualified,
    )
    try:
        session.add(record)
        session.commit()
        session.refresh(record)
        return record
    except Exception:
        session.rollback()
        raise


def parse_id_list(value: str) -> tuple[UUID, ...]:
    """Parse explicit comma-separated UUIDs for the developer CLI."""

    return tuple(UUID(part.strip()) for part in value.split(",") if part.strip())
