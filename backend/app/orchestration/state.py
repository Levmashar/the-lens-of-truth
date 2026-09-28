"""Safe persisted run creation, progress snapshots, and interrupted-run handling."""

import hashlib
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import LensError
from app.models.analysis_run import AnalysisRunRecord, ClaimAnalysisRunRecord
from app.schemas.analysis import CreateAnalysisRequest

ACTIVE = frozenset({"queued", "running"})
TERMINAL = frozenset({"completed", "failed", "partially_completed"})


def start_analysis(
    session: Session, request: CreateAnalysisRequest, *,
    idempotency_key: str | None, retention_hours: int,
) -> tuple[AnalysisRunRecord, bool]:
    """Reserve an opaque run before any slow provider call; deduplicate client retries."""

    if request.input.type == "url":
        raise LensError(501, "input_type_not_implemented", "URL analysis is not implemented.")
    if idempotency_key is not None and not re.fullmatch(r"[A-Za-z0-9._~-]{8,128}",
                                                       idempotency_key):
        raise LensError(422, "invalid_idempotency_key", "Invalid Idempotency-Key header.")
    request_hash = hashlib.sha256(request.model_dump_json(by_alias=True).encode()).hexdigest()
    key_hash = (hashlib.sha256(idempotency_key.encode()).hexdigest()
                if idempotency_key else None)
    if key_hash:
        existing = session.scalar(select(AnalysisRunRecord).where(
            AnalysisRunRecord.idempotency_key_hash == key_hash,
        ))
        if existing is not None:
            if existing.purge_after <= datetime.now(UTC):
                raise LensError(410, "idempotency_key_expired",
                                "This Idempotency-Key belongs to an expired analysis.")
            if existing.request_hash != request_hash:
                raise LensError(409, "idempotency_conflict",
                                "Idempotency-Key was used for a different request.")
            return existing, False
    row = AnalysisRunRecord(
        id=uuid4(), idempotency_key_hash=key_hash, request_hash=request_hash,
        status="queued", stage="queued", completed_stages=[], claim_count=0,
        stage_timestamps={},
        completed_claims=0, purge_after=datetime.now(UTC) + timedelta(hours=retention_hours),
        updated_at=datetime.now(UTC),
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        if key_hash:
            existing = session.scalar(select(AnalysisRunRecord).where(
                AnalysisRunRecord.idempotency_key_hash == key_hash,
            ))
            if existing is not None:
                if existing.purge_after <= datetime.now(UTC):
                    raise LensError(410, "idempotency_key_expired",
                                    "This Idempotency-Key belongs to an expired analysis.") \
                        from None
                if existing.request_hash != request_hash:
                    raise LensError(409, "idempotency_conflict",
                                    "Idempotency-Key was used for a different request.") from None
                return existing, False
        raise
    return row, True


def get_run(session: Session, analysis_id: UUID) -> AnalysisRunRecord:
    row = session.get(AnalysisRunRecord, analysis_id)
    if row is None or row.purge_after <= datetime.now(UTC):
        raise LensError(404, "analysis_not_found", "Analysis was not found or has expired.")
    return row


def claim_runs(session: Session, analysis_id: UUID) -> list[ClaimAnalysisRunRecord]:
    return list(session.scalars(select(ClaimAnalysisRunRecord).where(
        ClaimAnalysisRunRecord.analysis_run_id == analysis_id,
    ).order_by(ClaimAnalysisRunRecord.ordinal)))


def mark_interrupted(session: Session) -> int:
    """Single-worker startup: fail, never replay, work abandoned by a process restart."""

    rows = list(session.scalars(select(AnalysisRunRecord).where(
        AnalysisRunRecord.status.in_(ACTIVE),
    )))
    now = datetime.now(UTC)
    for row in rows:
        row.status = "failed"
        row.failure_code = "worker_interrupted"
        row.finished_at = now
        row.updated_at = now
        row.stage_timestamps = {**row.stage_timestamps, row.stage: {
            **row.stage_timestamps.get(row.stage, {}), "failed_at": now.isoformat(),
        }}
    for row in rows:
        for claim in claim_runs(session, row.id):
            if claim.status in ACTIVE:
                claim.status = "failed"
                claim.failure_code = "worker_interrupted"
                claim.finished_at = now
                claim.stage_timestamps = {**claim.stage_timestamps, claim.stage: {
                    **claim.stage_timestamps.get(claim.stage, {}),
                    "failed_at": now.isoformat(),
                }}
    session.commit()
    return len(rows)


def purge_expired_runs(session: Session) -> int:
    """Remove queued/pre-extraction metadata with the same short retention window."""

    rows = list(session.scalars(select(AnalysisRunRecord).where(
        AnalysisRunRecord.purge_after <= datetime.now(UTC),
    )))
    for row in rows:
        session.delete(row)
    session.commit()
    return len(rows)
