"""Append-only per-judge evidence-use validation records."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class JudgeValidationRunRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "judge_validation_run"
    __table_args__ = (
        Index("ix_judge_validation_run_judge_run_id", "judge_run_id"),
        Index("ix_judge_validation_run_evidence_pack_id", "evidence_pack_id"),
    )

    judge_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("judge_run.id", ondelete="CASCADE"), nullable=False,
    )
    evidence_pack_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("evidence_pack.id", ondelete="CASCADE"), nullable=False,
    )
    evidence_pack_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    deterministic_validator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    entailment_provider: Mapped[str | None] = mapped_column(String(64))
    entailment_model: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
