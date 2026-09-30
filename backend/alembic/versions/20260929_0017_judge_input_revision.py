"""Freeze judge-visible input and append-only semantic revision lineage.

Revision ID: 20260929_0017
Revises: 20260929_0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "20260929_0017"
down_revision: str | None = "20260929_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("judge_run", sa.Column("input_snapshot_version", sa.String(64)))
    op.add_column("judge_run", sa.Column("input_snapshot_hash", sa.String(64)))
    op.add_column("judge_run", sa.Column("input_snapshot_json", JSONB()))
    op.add_column("judge_run", sa.Column("revision_of_judge_run_id", UUID(as_uuid=True)))
    op.add_column("judge_run", sa.Column(
        "semantic_revision_number", sa.Integer(), nullable=False, server_default="0",
    ))
    op.create_foreign_key(
        "fk_judge_run_revision_parent", "judge_run", "judge_run",
        ["revision_of_judge_run_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index(
        "uq_judge_run_single_revision", "judge_run", ["revision_of_judge_run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_judge_run_single_revision", table_name="judge_run")
    op.drop_constraint("fk_judge_run_revision_parent", "judge_run", type_="foreignkey")
    op.drop_column("judge_run", "semantic_revision_number")
    op.drop_column("judge_run", "revision_of_judge_run_id")
    op.drop_column("judge_run", "input_snapshot_json")
    op.drop_column("judge_run", "input_snapshot_hash")
    op.drop_column("judge_run", "input_snapshot_version")
