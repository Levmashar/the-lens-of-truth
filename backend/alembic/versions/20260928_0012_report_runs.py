"""Phase 6C append-only deterministic report snapshots.

Revision ID: 20260928_0012
Revises: 20260928_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260928_0012"
down_revision: str | None = "20260928_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("verdict_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_version", sa.String(length=32), nullable=False),
        sa.Column("report_builder_version", sa.String(length=64), nullable=False),
        sa.Column("result_json", postgresql.JSONB(), nullable=False),
        sa.Column("semantic_hash", sa.String(length=64), nullable=False),
        sa.Column("production_qualified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["verdict_run_id"], ["verdict_run.id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_report_run_verdict_run_id", "report_run", ["verdict_run_id"])
    op.execute("""
        CREATE FUNCTION lens_reject_report_run_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'report_run is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_report_run_no_update
        BEFORE UPDATE ON report_run
        FOR EACH ROW EXECUTE FUNCTION lens_reject_report_run_update()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_report_run_no_update ON report_run")
    op.execute("DROP FUNCTION IF EXISTS lens_reject_report_run_update()")
    op.drop_index("ix_report_run_verdict_run_id", table_name="report_run")
    op.drop_table("report_run")
