"""Audit whether an atomic claim is independently understandable.

Revision ID: 20260929_0016
Revises: 20260929_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260929_0016"
down_revision: str | None = "20260929_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("claim", sa.Column("standalone_status", sa.String(length=24), nullable=True))


def downgrade() -> None:
    op.drop_column("claim", "standalone_status")
