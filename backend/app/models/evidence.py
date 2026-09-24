"""Evidence document and minimal-passage provenance models."""

from datetime import date, datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Bibliographic provenance; it deliberately avoids a full-text column."""

    __tablename__ = "evidence_document"
    __table_args__ = (
        Index("ix_evidence_document_pmid", "pmid"),
        Index("ix_evidence_document_doi", "doi"),
        Index("ix_evidence_document_canonical_url", "canonical_url", unique=True),
    )

    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_tier: Mapped[str | None] = mapped_column(String(8))
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    pmid: Mapped[str | None] = mapped_column(String(32))
    doi: Mapped[str | None] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retraction_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    license_code: Mapped[str | None] = mapped_column(String(128))
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    passages: Mapped[list["EvidencePassage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class EvidencePassage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A displayable evidence span and optional vector for future retrieval."""

    __tablename__ = "evidence_passage"
    __table_args__ = (Index("ix_evidence_passage_document_id", "document_id"),)

    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evidence_document.id", ondelete="CASCADE"),
        nullable=False,
    )
    section: Mapped[str | None] = mapped_column(String(128))
    char_start: Mapped[int | None] = mapped_column()
    char_end: Mapped[int | None] = mapped_column()
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    snippet_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))

    document: Mapped[EvidenceDocument] = relationship(back_populates="passages")
