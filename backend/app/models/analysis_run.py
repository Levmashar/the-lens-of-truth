"""Mutable orchestration checkpoints; medical artifacts remain append-only."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class AnalysisRunRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "analysis_run"
    __table_args__ = (Index("ix_analysis_run_purge_after", "purge_after"),)

    submission_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("submission.id", ondelete="CASCADE"), unique=True
    )
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    completed_stages: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    stage_timestamps: Mapped[dict[str, dict[str, str]]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_claims: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ClaimAnalysisRunRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "claim_analysis_run"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "claim_id"),
        Index("ix_claim_analysis_run_analysis", "analysis_run_id"),
    )

    analysis_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_run.id", ondelete="CASCADE"), nullable=False
    )
    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("claim.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    completed_stages: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    stage_timestamps: Mapped[dict[str, dict[str, str]]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    evidence_pack_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    evidence_pack_hash: Mapped[str | None] = mapped_column(String(64))
    judge_run_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    validation_run_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    verdict_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    report_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )
