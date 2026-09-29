"""Insert-only storage for successes and failures tied to one frozen pack."""

from sqlalchemy.orm import Session

from app.judging.models import JudgeRun
from app.models.judge_run import JudgeRunRecord
from app.models.retrieval import EvidencePackRecord


def persist_judge_runs(session: Session, runs: tuple[JudgeRun, ...]) -> None:
    """Append complete audit records; never update a previous model judgment."""

    try:
        for run in runs:
            pack = session.get(EvidencePackRecord, run.evidence_pack_id)
            if (
                pack is None or pack.claim_id != run.claim_id
                or pack.snapshot_hash != run.evidence_pack_hash
            ):
                raise ValueError("Judge run does not match the stored Evidence Pack")
            session.add(JudgeRunRecord(
                id=run.judge_run_id, claim_id=run.claim_id,
                evidence_pack_id=run.evidence_pack_id,
                evidence_pack_hash=run.evidence_pack_hash, slot=run.slot,
                provider=run.provider, model=run.model, model_family=run.model_family,
                model_snapshot=run.model_snapshot, prompt_version=run.prompt_version,
                schema_version_inferred=run.schema_version_inferred,
                model_identity_verified=run.model_identity_verified,
                model_family_verified=run.model_family_verified,
                search_override_active=run.search_override_active,
                search_guard_bypassed=run.search_guard_bypassed,
                search_isolation_verified=run.search_isolation_verified,
                prompt_hash=run.prompt_hash, requested_at=run.requested_at,
                responded_at=run.responded_at, latency_ms=run.latency_ms,
                attempt_count=run.attempt_count, outcome_status=run.outcome_status,
                response_json=run.response_json,
                decision_json=(run.decision.model_dump(mode="json") if run.decision else None),
                input_tokens=run.input_tokens, output_tokens=run.output_tokens,
                provider_request_id=run.provider_request_id,
                error_category=run.error_category,
            ))
        session.commit()
    except Exception:
        session.rollback()
        raise
