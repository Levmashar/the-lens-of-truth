"""Audit the development-only judge search guard override.

Revision ID: 20260926_0009
Revises: 20260925_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260926_0009"
down_revision: str | None = "20260925_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        "search_override_active", "search_guard_bypassed", "search_isolation_verified",
    ):
        op.add_column(
            "judge_run",
            sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    for column in (
        "search_isolation_verified", "search_guard_bypassed", "search_override_active",
    ):
        op.drop_column("judge_run", column)
