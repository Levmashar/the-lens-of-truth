"""Create the Phase 1 medical-verification persistence foundation.

Revision ID: 20260924_0001
Revises:
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260924_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create enum types, provenance-aware tables, and pgvector support."""

    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    input_type = postgresql.ENUM("text", "screenshot", "url", name="input_type", create_type=False)
    verdict_label = postgresql.ENUM(
        "SUPPORTED",
        "CONTRADICTED",
        "NOT_ENOUGH_EVIDENCE",
        "UNABLE_TO_VERIFY",
        name="verdict_label",
        create_type=False,
    )
    input_type.create(bind, checkfirst=True)
    verdict_label.create(bind, checkfirst=True)

    op.create_table(
        "submission",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("client", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("input_type", input_type, nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("privacy_notice_version", sa.String(length=64), nullable=False),
        sa.Column("consent_accepted", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_submission_content_sha256", "submission", ["content_sha256"])
    op.create_index("ix_submission_purge_after", "submission", ["purge_after"])

    op.create_table(
        "claim",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("span_start", sa.Integer()),
        sa.Column("span_end", sa.Integer()),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text()),
        sa.Column("claim_type", sa.String(length=64)),
        sa.Column("population", sa.Text()),
        sa.Column("intervention_or_exposure", sa.Text()),
        sa.Column("comparator", sa.Text()),
        sa.Column("outcome", sa.Text()),
        sa.Column("timeframe", sa.Text()),
        sa.Column("risk_class", sa.String(length=32), nullable=False),
        sa.Column("verifiability", sa.Float()),
        sa.Column("coreference_uncertain", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["submission_id"], ["submission.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("submission_id", "ordinal"),
    )

    op.create_table(
        "evidence_document",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("source_tier", sa.String(length=8)),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("pmid", sa.String(length=32)),
        sa.Column("doi", sa.String(length=512)),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("published_at", sa.Date()),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retraction_status", sa.String(length=32), nullable=False),
        sa.Column("license_code", sa.String(length=128)),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_evidence_document_pmid", "evidence_document", ["pmid"])
    op.create_index("ix_evidence_document_doi", "evidence_document", ["doi"])
    op.create_index(
        "ix_evidence_document_canonical_url", "evidence_document", ["canonical_url"], unique=True
    )

    op.create_table(
        "evidence_passage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section", sa.String(length=128)),
        sa.Column("char_start", sa.Integer()),
        sa.Column("char_end", sa.Integer()),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("snippet_sha256", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(dim=1024)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["evidence_document.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_evidence_passage_document_id", "evidence_passage", ["document_id"])

    op.create_table(
        "model_evaluation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_provider", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("model_snapshot", sa.String(length=128)),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("label", verdict_label),
        sa.Column("probabilities", postgresql.JSONB()),
        sa.Column("groundedness", sa.Float()),
        sa.Column("evidence_coverage", sa.Float()),
        sa.Column("rationale", sa.Text()),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("provider_request_id", sa.String(length=256)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["claim_id"], ["claim.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "final_verdict",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", verdict_label, nullable=False),
        sa.Column("calibrated_confidence", sa.Float()),
        sa.Column("disagreement_jsd", sa.Float()),
        sa.Column("evidence_coverage", sa.Float()),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("evidence_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("requires_medical_review", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["claim_id"], ["claim.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("claim_id"),
    )


def downgrade() -> None:
    """Remove Phase 1 tables and types in reverse dependency order."""

    op.drop_table("final_verdict")
    op.drop_table("model_evaluation")
    op.drop_index("ix_evidence_passage_document_id", table_name="evidence_passage")
    op.drop_table("evidence_passage")
    op.drop_index("ix_evidence_document_canonical_url", table_name="evidence_document")
    op.drop_index("ix_evidence_document_doi", table_name="evidence_document")
    op.drop_index("ix_evidence_document_pmid", table_name="evidence_document")
    op.drop_table("evidence_document")
    op.drop_table("claim")
    op.drop_index("ix_submission_purge_after", table_name="submission")
    op.drop_index("ix_submission_content_sha256", table_name="submission")
    op.drop_table("submission")

    bind = op.get_bind()
    postgresql.ENUM(name="verdict_label").drop(bind, checkfirst=True)
    postgresql.ENUM(name="input_type").drop(bind, checkfirst=True)
