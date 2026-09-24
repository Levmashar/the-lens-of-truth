"""Persist grounded PICO and terminology-linking state on claims.

Revision ID: 20260924_0005
Revises: 20260924_0004
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20260924_0005"
down_revision: str | None = "20260924_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Leave prior claims explicitly pending; do not fabricate historical links."""

    op.add_column("claim", sa.Column("linked_entities", JSONB(), nullable=True))
    op.add_column("claim", sa.Column("pico_json", JSONB(), nullable=True))
    op.add_column(
        "claim",
        sa.Column(
            "normalization_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
    )


def downgrade() -> None:
    """Remove Phase 3A normalization columns."""

    op.drop_column("claim", "normalization_status")
    op.drop_column("claim", "pico_json")
    op.drop_column("claim", "linked_entities")
