"""Hash-bound inserts and reads; document audits are never overwritten."""

import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.document.models import canonical_document_hash
from app.models.document_run import DocumentRunRecord

DocumentArtifactKind = Literal[
    "plan",
    "group_evidence",
    "group_judge",
    "group_validation",
    "group_result",
    "report",
    "error",
]


def insert_document_artifact(
    session: Session,
    analysis_id: UUID,
    kind: DocumentArtifactKind,
    snapshot: dict[str, object],
    group_id: str | None = None,
    slot: int | None = None,
) -> DocumentRunRecord:
    """Append a detached canonical JSON artifact within the caller's session."""
    if slot is not None and slot not in {1, 2, 3}:
        raise ValueError("Document judge slot must be 1, 2 or 3")
    # Detach mutable caller dictionaries and reject non-JSON protocol objects.
    detached = json.loads(json.dumps(snapshot, ensure_ascii=False, allow_nan=False))
    version = detached.get("version", f"document-{kind.replace('_', '-')}-1.0")
    if not isinstance(version, str) or not 1 <= len(version) <= 64:
        raise ValueError("Document artifact requires a bounded version")
    row = DocumentRunRecord(
        id=uuid4(),
        analysis_id=analysis_id,
        kind=kind,
        version=version,
        group_id=group_id,
        slot=slot,
        snapshot_json=detached,
        snapshot_hash=canonical_document_hash(detached),
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    return row


def load_document_artifacts(
    session: Session,
    analysis_id: UUID,
    kind: DocumentArtifactKind | None = None,
) -> list[DocumentRunRecord]:
    """Read only this analysis; reject corrupted shared or per-judge snapshots."""
    query = select(DocumentRunRecord).where(DocumentRunRecord.analysis_id == analysis_id)
    if kind is not None:
        query = query.where(DocumentRunRecord.kind == kind)
    rows = list(session.scalars(query.order_by(DocumentRunRecord.created_at, DocumentRunRecord.id)))
    for row in rows:
        if canonical_document_hash(row.snapshot_json) != row.snapshot_hash:
            raise ValueError("Document artifact snapshot hash mismatch")
    return rows


def latest_document_artifact(
    session: Session,
    analysis_id: UUID,
    kind: DocumentArtifactKind,
) -> DocumentRunRecord | None:
    rows = load_document_artifacts(session, analysis_id, kind)
    return rows[-1] if rows else None
