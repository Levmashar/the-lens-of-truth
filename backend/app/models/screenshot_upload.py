"""Short-lived, privacy-aware screenshot upload metadata."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.submission import Submission


class ScreenshotUpload(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Metadata for a sanitized image held outside PostgreSQL for at most 24 hours.

    The database never contains raw image bytes or unredacted OCR text. ``object_key``
    is resolved only by the configured storage adapter.
    """

    __tablename__ = "screenshot_upload"
    __table_args__ = (
        Index("ix_screenshot_upload_content_sha256", "content_sha256"),
        Index("ix_screenshot_upload_purge_after", "purge_after"),
    )

    submission_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("submission.id", ondelete="CASCADE"),
        unique=True,
        nullable=True,
    )
    object_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    ocr_provider: Mapped[str | None] = mapped_column(String(64))
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    pii_redaction_count: Mapped[int | None] = mapped_column(Integer)
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    submission: Mapped["Submission | None"] = relationship(back_populates="screenshot_upload")
