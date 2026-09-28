"""Phase 7A durable orchestration checkpoints.

Revision ID: 20260928_0013
Revises: 20260928_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260928_0013"
down_revision: str | None = "20260928_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), unique=True),
        sa.Column("idempotency_key_hash", sa.String(64), unique=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("completed_stages", postgresql.JSONB(), nullable=False),
        sa.Column("claim_count", sa.Integer(), nullable=False),
        sa.Column("completed_claims", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["submission.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_analysis_run_purge_after", "analysis_run", ["purge_after"])
    op.create_table(
        "claim_analysis_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("completed_stages", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_pack_id", postgresql.UUID(as_uuid=True)),
        sa.Column("evidence_pack_hash", sa.String(64)),
        sa.Column("judge_run_ids", postgresql.JSONB(), nullable=False),
        sa.Column("validation_run_ids", postgresql.JSONB(), nullable=False),
        sa.Column("verdict_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("report_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_run.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claim_id"], ["claim.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("analysis_run_id", "claim_id"),
    )
    op.create_index("ix_claim_analysis_run_analysis", "claim_analysis_run",
                    ["analysis_run_id"])


def downgrade() -> None:
    op.drop_index("ix_claim_analysis_run_analysis", table_name="claim_analysis_run")
    op.drop_table("claim_analysis_run")
    op.drop_index("ix_analysis_run_purge_after", table_name="analysis_run")
    op.drop_table("analysis_run")
