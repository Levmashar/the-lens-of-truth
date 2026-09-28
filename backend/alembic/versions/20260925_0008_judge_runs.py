"""Append-only Phase 5A independent judge-run provenance.

Revision ID: 20260925_0008
Revises: 20260924_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260925_0008"
down_revision: str | None = "20260924_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "judge_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_pack_hash", sa.String(length=64), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("model_family", sa.String(length=64), nullable=False),
        sa.Column("model_snapshot", sa.String(length=128)),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("outcome_status", sa.String(length=16), nullable=False),
        sa.Column("response_json", postgresql.JSONB()),
        sa.Column("decision_json", postgresql.JSONB()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("provider_request_id", sa.String(length=128)),
        sa.Column("error_category", sa.String(length=64)),
        sa.ForeignKeyConstraint(["claim_id"], ["claim.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evidence_pack_id"], ["evidence_pack.id"], ondelete="CASCADE",
        ),
    )
    op.create_index("ix_judge_run_claim_id", "judge_run", ["claim_id"])
    op.create_index("ix_judge_run_evidence_pack_id", "judge_run", ["evidence_pack_id"])
    op.execute("""
        CREATE FUNCTION lens_reject_judge_run_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'judge_run is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_judge_run_no_update
        BEFORE UPDATE ON judge_run
        FOR EACH ROW EXECUTE FUNCTION lens_reject_judge_run_update()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_judge_run_no_update ON judge_run")
    op.execute("DROP FUNCTION IF EXISTS lens_reject_judge_run_update()")
    op.drop_index("ix_judge_run_evidence_pack_id", table_name="judge_run")
    op.drop_index("ix_judge_run_claim_id", table_name="judge_run")
    op.drop_table("judge_run")
