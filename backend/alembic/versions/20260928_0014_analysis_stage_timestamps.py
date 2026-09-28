"""Phase 7A per-stage timing checkpoints.

Revision ID: 20260928_0014
Revises: 20260928_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260928_0014"
down_revision: str | None = "20260928_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("analysis_run", "claim_analysis_run"):
        op.add_column(table, sa.Column(
            "stage_timestamps", postgresql.JSONB(), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ))


def downgrade() -> None:
    for table in ("claim_analysis_run", "analysis_run"):
        op.drop_column(table, "stage_timestamps")
