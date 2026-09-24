"""Record semantic extraction provider, model, and prompt version.

Revision ID: 20260924_0004
Revises: 20260924_0003
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0004"
down_revision: str | None = "20260924_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add non-secret metadata that identifies a real extraction run."""

    op.add_column("submission", sa.Column("extraction_provider", sa.String(length=64), nullable=True))
    op.add_column("submission", sa.Column("extraction_model", sa.String(length=128), nullable=True))
    op.add_column(
        "submission", sa.Column("extraction_prompt_version", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    """Remove Phase 2 extraction audit metadata."""

    op.drop_column("submission", "extraction_prompt_version")
    op.drop_column("submission", "extraction_model")
    op.drop_column("submission", "extraction_provider")
