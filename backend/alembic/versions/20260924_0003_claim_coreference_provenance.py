"""Preserve the antecedent span used for unambiguous claim coreference.

Revision ID: 20260924_0003
Revises: 20260924_0002
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0003"
down_revision: str | None = "20260924_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable antecedent offsets to the existing atomic-claim record."""

    op.add_column("claim", sa.Column("resolved_from_span_start", sa.Integer(), nullable=True))
    op.add_column("claim", sa.Column("resolved_from_span_end", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Remove Phase 2 coreference provenance."""

    op.drop_column("claim", "resolved_from_span_end")
    op.drop_column("claim", "resolved_from_span_start")
