"""Record explicit protocol-only schema version inference on judge runs.

Revision ID: 20260929_0015
Revises: 20260928_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260929_0015"
down_revision: str | None = "20260928_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "judge_run",
        sa.Column(
            "schema_version_inferred", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("judge_run", "schema_version_inferred")
