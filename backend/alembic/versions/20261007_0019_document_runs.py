"""Versioned append-only document plan, shared evidence and grouped audits."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261007_0019"
down_revision: str | None = "20261001_0018"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "document_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("group_id", sa.String(32)),
        sa.Column("slot", sa.Integer()),
        sa.Column("snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["analysis_id"], ["analysis_run.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_document_run_analysis_kind", "document_run", ["analysis_id", "kind"])
    op.execute("""
        CREATE FUNCTION lens_reject_document_run_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'document_run is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_document_run_no_update
        BEFORE UPDATE ON document_run
        FOR EACH ROW EXECUTE FUNCTION lens_reject_document_run_update()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_document_run_no_update ON document_run")
    op.execute("DROP FUNCTION IF EXISTS lens_reject_document_run_update()")
    op.drop_index("ix_document_run_analysis_kind", table_name="document_run")
    op.drop_table("document_run")
