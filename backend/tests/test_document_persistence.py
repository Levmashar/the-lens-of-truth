"""Detached, hash-bound, append-only document artifacts and retention regressions."""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db.session import SessionLocal
from app.document.models import canonical_document_hash
from app.document.persistence import insert_document_artifact, load_document_artifacts
from app.models.analysis_run import AnalysisRunRecord
from app.models.document_run import DocumentRunRecord


def test_insert_detaches_caller_and_hashes_exact_snapshot() -> None:
    session = Mock()
    snapshot = {"version": "document-report-1.0", "items": [{"value": "original"}]}
    row = insert_document_artifact(session, uuid4(), "report", snapshot)
    snapshot["items"][0]["value"] = "changed"
    assert row.snapshot_json["items"][0]["value"] == "original"
    assert row.snapshot_hash == canonical_document_hash(row.snapshot_json)
    session.add.assert_called_once_with(row)
    session.commit.assert_called_once()


@pytest.mark.parametrize("snapshot", [{"version": ""}, {"version": "v" * 65}, {"x": float("nan")}])
def test_invalid_protocol_snapshots_are_not_inserted(snapshot: dict[str, object]) -> None:
    session = Mock()
    with pytest.raises(ValueError):
        insert_document_artifact(session, uuid4(), "report", snapshot)
    session.add.assert_not_called()


def test_corrupted_snapshot_hash_fails_closed() -> None:
    session = Mock()
    row = insert_document_artifact(session, uuid4(), "report", {"items": []})
    row.snapshot_json["items"].append("corrupted")
    session.scalars.return_value = [row]
    with pytest.raises(ValueError, match="hash mismatch"):
        load_document_artifacts(session, row.analysis_id, "report")


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires migrated PostgreSQL")
def test_postgres_append_only_scope_and_retention_cascade() -> None:
    analysis_id, other_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    with SessionLocal() as session:
        for identifier in (analysis_id, other_id):
            session.add(AnalysisRunRecord(
                id=identifier, request_hash="f" * 64, status="completed", stage="completed",
                completed_stages=[], stage_timestamps={}, claim_count=0, completed_claims=0,
                purge_after=now + timedelta(hours=1), updated_at=now,
            ))
        session.commit()
        try:
            first = insert_document_artifact(session, analysis_id, "plan", {"text": "source"})
            insert_document_artifact(session, analysis_id, "report", {"items": []})
            insert_document_artifact(session, other_id, "report", {"items": ["other"]})
            assert len(load_document_artifacts(session, analysis_id)) == 2
            assert load_document_artifacts(session, analysis_id, "report")[0].snapshot_json == {
                "items": [],
            }
            with pytest.raises(DBAPIError, match="append-only"):
                session.execute(text("UPDATE document_run SET version='tampered' WHERE id=:id"),
                                {"id": first.id})
                session.commit()
            session.rollback()
            session.delete(session.get(AnalysisRunRecord, analysis_id))
            session.commit()
            assert not list(session.scalars(select(DocumentRunRecord).where(
                DocumentRunRecord.analysis_id == analysis_id,
            )))
            assert len(load_document_artifacts(session, other_id)) == 1
        finally:
            session.rollback()
            for identifier in (analysis_id, other_id):
                run = session.get(AnalysisRunRecord, identifier)
                if run is not None:
                    session.delete(run)
            session.commit()
