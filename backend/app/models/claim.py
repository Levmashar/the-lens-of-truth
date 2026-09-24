"""Atomic claim persistence model."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.evaluation import FinalVerdict, ModelEvaluation
    from app.models.submission import Submission


class Claim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One independently verifiable proposition with source offsets and PICO slots."""

    __tablename__ = "claim"
    __table_args__ = (UniqueConstraint("submission_id", "ordinal"),)

    submission_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("submission.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    span_start: Mapped[int | None] = mapped_column(Integer)
    span_end: Mapped[int | None] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    claim_type: Mapped[str | None] = mapped_column(String(64))
    population: Mapped[str | None] = mapped_column(Text)
    intervention_or_exposure: Mapped[str | None] = mapped_column(Text)
    comparator: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text)
    timeframe: Mapped[str | None] = mapped_column(Text)
    linked_entities: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    pico_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    normalization_quality: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    normalization_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    risk_class: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")
    verifiability: Mapped[float | None] = mapped_column(Float)
    coreference_uncertain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_from_span_start: Mapped[int | None] = mapped_column(Integer)
    resolved_from_span_end: Mapped[int | None] = mapped_column(Integer)

    submission: Mapped["Submission"] = relationship(back_populates="claims")
    model_evaluations: Mapped[list["ModelEvaluation"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    final_verdict: Mapped["FinalVerdict | None"] = relationship(
        back_populates="claim", cascade="all, delete-orphan", uselist=False
    )
