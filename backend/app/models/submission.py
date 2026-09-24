"""Submission persistence model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import InputType

if TYPE_CHECKING:
    from app.models.claim import Claim
    from app.models.screenshot_upload import ScreenshotUpload


class Submission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Privacy-aware metadata for one analysis request.

    Raw content is intentionally not modeled here. Future ingestion must route
    short-lived raw assets to an approved storage adapter and retain only safe
    metadata/hashes in the relational record.
    """

    __tablename__ = "submission"
    __table_args__ = (
        Index("ix_submission_content_sha256", "content_sha256"),
        Index("ix_submission_purge_after", "purge_after"),
    )

    client: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")
    input_type: Mapped[InputType] = mapped_column(
        Enum(InputType, name="input_type"), nullable=False
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    privacy_notice_version: Mapped[str] = mapped_column(String(64), nullable=False)
    consent_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="received")
    extraction_provider: Mapped[str | None] = mapped_column(String(64))
    extraction_model: Mapped[str | None] = mapped_column(String(128))
    extraction_prompt_version: Mapped[str | None] = mapped_column(String(64))
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    claims: Mapped[list["Claim"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
    screenshot_upload: Mapped["ScreenshotUpload | None"] = relationship(
        back_populates="submission", uselist=False
    )
