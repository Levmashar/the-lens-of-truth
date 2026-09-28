"""Append-only snapshots of deterministic, internal human-readable reports."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class ReportRunRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "report_run"
    __table_args__ = (Index("ix_report_run_verdict_run_id", "verdict_run_id"),)

    verdict_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("verdict_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_version: Mapped[str] = mapped_column(String(32), nullable=False)
    report_builder_version: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    semantic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    production_qualified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
