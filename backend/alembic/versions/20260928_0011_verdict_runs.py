"""Phase 6B explicit qualification audit and append-only verdict runs.

Revision ID: 20260928_0011
Revises: 20260928_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260928_0011"
down_revision: str | None = "20260928_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("model_identity_verified", "model_family_verified"):
        op.add_column(
            "judge_run",
            sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.create_table(
        "verdict_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_pack_hash", sa.String(length=64), nullable=False),
        sa.Column("judge_run_ids", postgresql.JSONB(), nullable=False),
        sa.Column("judge_validation_run_ids", postgresql.JSONB(), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False),
        sa.Column("result_json", postgresql.JSONB(), nullable=False),
        sa.Column("semantic_hash", sa.String(length=64), nullable=False),
        sa.Column("production_qualified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claim.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_pack_id"], ["evidence_pack.id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_verdict_run_claim_id", "verdict_run", ["claim_id"])
    op.create_index("ix_verdict_run_evidence_pack_id", "verdict_run", ["evidence_pack_id"])
    op.execute("""
        CREATE FUNCTION lens_reject_verdict_run_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'verdict_run is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_verdict_run_no_update
        BEFORE UPDATE ON verdict_run
        FOR EACH ROW EXECUTE FUNCTION lens_reject_verdict_run_update()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_verdict_run_no_update ON verdict_run")
    op.execute("DROP FUNCTION IF EXISTS lens_reject_verdict_run_update()")
    op.drop_index("ix_verdict_run_evidence_pack_id", table_name="verdict_run")
    op.drop_index("ix_verdict_run_claim_id", table_name="verdict_run")
    op.drop_table("verdict_run")
    for column in ("model_family_verified", "model_identity_verified"):
        op.drop_column("judge_run", column)
