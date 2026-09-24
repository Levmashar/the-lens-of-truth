"""Versioned PubMed documents and immutable retrieval-pack persistence.

Revision ID: 20260924_0007
Revises: 20260924_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260924_0007"
down_revision: str | None = "20260924_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence_document", sa.Column("abstract", sa.Text()))
    op.add_column("evidence_document", sa.Column("abstract_sections", postgresql.JSONB()))
    op.add_column("evidence_document", sa.Column("journal", sa.Text()))
    op.add_column("evidence_document", sa.Column("authors", postgresql.JSONB()))
    op.add_column("evidence_document", sa.Column("publication_types", postgresql.JSONB()))
    op.add_column("evidence_document", sa.Column("mesh_terms", postgresql.JSONB()))
    op.add_column("evidence_document", sa.Column("language", sa.String(length=32)))
    op.drop_index("ix_evidence_document_canonical_url", table_name="evidence_document")
    op.create_index("ix_evidence_document_canonical_url", "evidence_document", ["canonical_url"])
    op.create_unique_constraint(
        "uq_evidence_document_source_kind", "evidence_document",
        ["source_kind", "pmid", "content_sha256"],
    )

    op.create_table(
        "retrieval_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("query_plan_json", postgresql.JSONB(), nullable=False),
        sa.Column("diagnostics_json", postgresql.JSONB(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claim.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_retrieval_run_claim_id", "retrieval_run", ["claim_id"])
    op.create_table(
        "retrieval_query",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", sa.String(length=16), nullable=False),
        sa.Column("family", sa.String(length=32), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("source_fields", postgresql.JSONB(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["retrieval_run.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "query_id"),
    )
    op.create_table(
        "retrieval_document_query",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["evidence_document.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_id"], ["retrieval_query.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id", "query_id"),
    )
    op.create_table(
        "evidence_pack",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(length=16), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claim.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["retrieval_run.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_evidence_pack_claim_id", "evidence_pack", ["claim_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_pack_claim_id", table_name="evidence_pack")
    op.drop_table("evidence_pack")
    op.drop_table("retrieval_document_query")
    op.drop_table("retrieval_query")
    op.drop_index("ix_retrieval_run_claim_id", table_name="retrieval_run")
    op.drop_table("retrieval_run")
    op.drop_constraint("uq_evidence_document_source_kind", "evidence_document", type_="unique")
    op.drop_index("ix_evidence_document_canonical_url", table_name="evidence_document")
    op.create_index("ix_evidence_document_canonical_url", "evidence_document",
                    ["canonical_url"], unique=True)
    for column in (
        "language", "mesh_terms", "publication_types", "authors", "journal",
        "abstract_sections", "abstract",
    ):
        op.drop_column("evidence_document", column)
