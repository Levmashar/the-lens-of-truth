"""Append-only audit rows for individual model-family judging attempts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class JudgeRunRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "judge_run"
    __table_args__ = (
        Index("ix_judge_run_claim_id", "claim_id"),
        Index("ix_judge_run_evidence_pack_id", "evidence_pack_id"),
    )

    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("claim.id", ondelete="CASCADE"), nullable=False,
    )
    evidence_pack_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("evidence_pack.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_pack_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    model_family: Mapped[str] = mapped_column(String(64), nullable=False)
    model_snapshot: Mapped[str | None] = mapped_column(String(128))
    search_override_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
    )
    search_guard_bypassed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
    )
    search_isolation_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
    )
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome_status: Mapped[str] = mapped_column(String(16), nullable=False)
    response_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    decision_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    provider_request_id: Mapped[str | None] = mapped_column(String(128))
    error_category: Mapped[str | None] = mapped_column(String(64))
