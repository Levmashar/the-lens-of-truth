"""Add short-lived screenshot upload metadata for Phase 2 ingestion.

Revision ID: 20260924_0002
Revises: 20260924_0001
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260924_0002"
down_revision: str | None = "20260924_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create metadata only; sanitized raw image bytes remain in upload storage."""

    op.create_table(
        "screenshot_upload",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("object_key", sa.String(length=255), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("ocr_provider", sa.String(length=64), nullable=True),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("pii_redaction_count", sa.Integer(), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["submission_id"], ["submission.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("object_key"),
        sa.UniqueConstraint("submission_id"),
    )
    op.create_index(
        "ix_screenshot_upload_content_sha256", "screenshot_upload", ["content_sha256"]
    )
    op.create_index("ix_screenshot_upload_purge_after", "screenshot_upload", ["purge_after"])


def downgrade() -> None:
    """Remove Phase 2 screenshot metadata."""

    op.drop_index("ix_screenshot_upload_purge_after", table_name="screenshot_upload")
    op.drop_index("ix_screenshot_upload_content_sha256", table_name="screenshot_upload")
    op.drop_table("screenshot_upload")
