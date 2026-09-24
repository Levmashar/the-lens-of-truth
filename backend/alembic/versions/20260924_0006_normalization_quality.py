"""Persist source-grounded normalization completeness metadata.

Revision ID: 20260924_0006
Revises: 20260924_0005
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20260924_0006"
down_revision: str | None = "20260924_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Do not grandfather unaudited legacy rows into the stronger normalized state."""

    op.add_column("claim", sa.Column("normalization_quality", JSONB(), nullable=True))
    op.execute(
        "UPDATE claim SET normalization_status = 'partial', "
        "normalization_quality = '{\"normalization_coverage\": null, "
        "\"missing_explicit_concepts\": [], \"required_slots_missing\": [], "
        "\"ambiguous_concepts\": [], "
        "\"normalization_warnings\": [\"legacy_not_audited\"]}'::jsonb "
        "WHERE normalization_status = 'normalized'"
    )


def downgrade() -> None:
    op.drop_column("claim", "normalization_quality")
