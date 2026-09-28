"""Append-only deterministic aggregation audits, distinct from the legacy final_verdict."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class VerdictRunRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "verdict_run"
    __table_args__ = (
        Index("ix_verdict_run_claim_id", "claim_id"),
        Index("ix_verdict_run_evidence_pack_id", "evidence_pack_id"),
    )

    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("claim.id", ondelete="CASCADE"), nullable=False,
    )
    evidence_pack_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("evidence_pack.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_pack_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    judge_run_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    judge_validation_run_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    result_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    production_qualified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
