"""Append-only Phase 6A per-judge validation audit.

Revision ID: 20260928_0010
Revises: 20260926_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260928_0010"
down_revision: str | None = "20260926_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "judge_validation_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("judge_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_pack_hash", sa.String(length=64), nullable=False),
        sa.Column("validation_version", sa.String(length=64), nullable=False),
        sa.Column("deterministic_validator_version", sa.String(length=128), nullable=False),
        sa.Column("entailment_provider", sa.String(length=64)),
        sa.Column("entailment_model", sa.String(length=128)),
        sa.Column("prompt_version", sa.String(length=64)),
        sa.Column("prompt_hash", sa.String(length=64)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_json", postgresql.JSONB(), nullable=False),
        sa.Column("error_category", sa.String(length=64)),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["judge_run_id"], ["judge_run.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_pack_id"], ["evidence_pack.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_judge_validation_run_judge_run_id", "judge_validation_run",
                    ["judge_run_id"])
    op.create_index("ix_judge_validation_run_evidence_pack_id", "judge_validation_run",
                    ["evidence_pack_id"])
    op.execute("""
        CREATE FUNCTION lens_reject_judge_validation_run_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'judge_validation_run is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_judge_validation_run_no_update
        BEFORE UPDATE ON judge_validation_run
        FOR EACH ROW EXECUTE FUNCTION lens_reject_judge_validation_run_update()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_judge_validation_run_no_update "
               "ON judge_validation_run")
    op.execute("DROP FUNCTION IF EXISTS lens_reject_judge_validation_run_update()")
    op.drop_index("ix_judge_validation_run_evidence_pack_id",
                  table_name="judge_validation_run")
    op.drop_index("ix_judge_validation_run_judge_run_id",
                  table_name="judge_validation_run")
    op.drop_table("judge_validation_run")
