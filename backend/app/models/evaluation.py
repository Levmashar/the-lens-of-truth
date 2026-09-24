"""Model-evaluation and final-verdict audit models."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import VerdictLabel

if TYPE_CHECKING:
    from app.models.claim import Claim


class ModelEvaluation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One structured judge result, retained for calibration and auditability."""

    __tablename__ = "model_evaluation"

    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("claim.id", ondelete="CASCADE"), nullable=False
    )
    model_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    model_snapshot: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[VerdictLabel | None] = mapped_column(Enum(VerdictLabel, name="verdict_label"))
    probabilities: Mapped[dict[str, float] | None] = mapped_column(JSONB)
    groundedness: Mapped[float | None] = mapped_column(Float)
    evidence_coverage: Mapped[float | None] = mapped_column(Float)
    rationale: Mapped[str | None] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    provider_request_id: Mapped[str | None] = mapped_column(String(256))

    claim: Mapped["Claim"] = relationship(back_populates="model_evaluations")


class FinalVerdict(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One deterministic aggregation record per claim, populated in Phase 5."""

    __tablename__ = "final_verdict"
    __table_args__ = (UniqueConstraint("claim_id"),)

    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("claim.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[VerdictLabel] = mapped_column(
        Enum(VerdictLabel, name="verdict_label"), nullable=False
    )
    calibrated_confidence: Mapped[float | None] = mapped_column(Float)
    disagreement_jsd: Mapped[float | None] = mapped_column(Float)
    evidence_coverage: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    requires_medical_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    claim: Mapped["Claim"] = relationship(back_populates="final_verdict")
