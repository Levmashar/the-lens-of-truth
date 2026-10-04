"""Preserve official source headings without truncation or artifact rewrites."""

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0018"
down_revision: str | None = "20260929_0017"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column("evidence_passage", "section", existing_type=sa.String(128),
                    type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    # Never silently destroy exact headings in historical frozen artifacts.
    if op.get_bind().scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM evidence_passage WHERE length(section) > 128)"
    )):
        raise RuntimeError("Cannot downgrade while retained headings exceed 128 characters")
    op.alter_column("evidence_passage", "section", existing_type=sa.Text(),
                    type_=sa.String(128), existing_nullable=True)
