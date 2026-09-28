"""Insert-only persistence with judge/pack identity checks."""

from sqlalchemy.orm import Session

from app.models.judge_run import JudgeRunRecord
from app.models.judge_validation_run import JudgeValidationRunRecord
from app.models.retrieval import EvidencePackRecord
from app.validation.models import IssueCode, JudgeValidationRun


def persist_validation_run(session: Session, run: JudgeValidationRun) -> None:
    judge = session.get(JudgeRunRecord, run.judge_run_id)
    pack = session.get(EvidencePackRecord, run.evidence_pack_id)
    if (judge is None or pack is None or judge.evidence_pack_id != pack.id
            or judge.evidence_pack_hash != run.evidence_pack_hash
            or judge.decision_json is None or run.result.judge_run_id != judge.id
            or run.result.evidence_pack_id != pack.id):
        raise ValueError("Validation run does not match a successful stored judge/pack")
    if (pack.snapshot_hash != run.evidence_pack_hash
            and IssueCode.PACK_HASH_MISMATCH not in run.result.fatal_issue_codes):
        raise ValueError("A pack hash discrepancy must be recorded as fatal")
    try:
        session.add(JudgeValidationRunRecord(
            id=run.id, judge_run_id=run.judge_run_id,
            evidence_pack_id=run.evidence_pack_id,
            evidence_pack_hash=run.evidence_pack_hash,
            validation_version=run.validation_version,
            deterministic_validator_version=run.deterministic_validator_version,
            entailment_provider=run.entailment_provider, entailment_model=run.entailment_model,
            prompt_version=run.prompt_version, prompt_hash=run.prompt_hash,
            started_at=run.started_at, completed_at=run.completed_at,
            status=run.status.value, result_json=run.result.model_dump(mode="json"),
            error_category=run.error_category, latency_ms=run.latency_ms,
            attempt_count=run.attempt_count,
        ))
        session.commit()
    except Exception:
        session.rollback()
        raise
