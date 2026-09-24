"""Append-only retrieval runs, query provenance, and frozen pack snapshots."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RetrievalRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "retrieval_run"
    __table_args__ = (Index("ix_retrieval_run_claim_id", "claim_id"),)

    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("claim.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    query_plan_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    diagnostics_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RetrievalQuery(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "retrieval_query"
    __table_args__ = (UniqueConstraint("run_id", "query_id"),)

    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("retrieval_run.id", ondelete="CASCADE"), nullable=False
    )
    query_id: Mapped[str] = mapped_column(String(16), nullable=False)
    family: Mapped[str] = mapped_column(String(32), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(nullable=False)


class RetrievalDocumentQuery(Base):
    __tablename__ = "retrieval_document_query"

    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("evidence_document.id", ondelete="CASCADE"),
        primary_key=True,
    )
    query_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("retrieval_query.id", ondelete="CASCADE"),
        primary_key=True,
    )


class EvidencePackRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "evidence_pack"
    __table_args__ = (Index("ix_evidence_pack_claim_id", "claim_id"),)

    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("claim.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("retrieval_run.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
