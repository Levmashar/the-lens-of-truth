"""Document HTTP progress/report flow, public gates, privacy and audit failures."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes import analyses
from app.core.config import Settings, get_runtime_settings
from app.db.session import get_db_session
from app.document.models import canonical_document_hash
from app.document.persistence import insert_document_artifact
from app.models.analysis_run import AnalysisRunRecord
from tests.test_document_audit import fixture as audit_fixture


class DocumentSession:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.run = AnalysisRunRecord(
            id=uuid4(),
            request_hash="a" * 64,
            status="completed",
            stage="completed",
            completed_stages=[],
            stage_timestamps={"document": {"mode": "document"}},
            claim_count=2,
            completed_claims=2,
            purge_after=now + timedelta(hours=1),
            updated_at=now,
        )
        self.rows = []

    def get(self, model: type, identifier: UUID) -> object | None:
        return self.run if model is AnalysisRunRecord and identifier == self.run.id else None

    def add(self, row: object) -> None:
        self.rows.append(row)

    def commit(self) -> None:
        pass

    def scalars(self, query: object) -> list[object]:
        if query.column_descriptions[0]["entity"].__name__ != "DocumentRunRecord":
            return []
        parameters = query.compile().params
        values = tuple(parameters.values())
        kinds = {"plan", "group_evidence", "group_judge", "report", "error"}
        selected_kind = next((value for value in values if value in kinds), None)
        return sorted(
            (
                row
                for row in self.rows
                if row.analysis_id in values
                and (selected_kind is None or row.kind == selected_kind)
            ),
            key=lambda row: (row.created_at, row.id),
        )


@pytest.fixture
def document_client(client: TestClient, monkeypatch):
    session = DocumentSession()
    analysis_id, report, plan_row, evidence_rows, judge_rows = audit_fixture(monkeypatch)
    session.run.id = analysis_id
    for row in [plan_row, *evidence_rows, *judge_rows]:
        insert_document_artifact(
            session, analysis_id, row.kind, row.snapshot_json, row.group_id, row.slot
        )
    insert_document_artifact(session, session.run.id, "report", report)
    client.app.dependency_overrides[get_db_session] = lambda: session
    client.app.dependency_overrides[get_runtime_settings] = lambda: Settings(
        _env_file=None,
        app_env="test",
        debug_mode=False,
    )
    yield client, session
    client.app.dependency_overrides.clear()


def test_saved_document_progress_and_readable_report_require_no_calls(document_client) -> None:
    client, session = document_client
    progress = client.get(f"/v1/analyses/{session.run.id}")
    assert progress.status_code == 200
    assert progress.json()["document_mode"] is True
    assert progress.json()["claims"] == []
    response = client.get(f"/v1/analyses/{session.run.id}/document")
    assert response.status_code == 200
    report = response.json()
    assert report["version"] == "document-report-1.0"
    assert report["progress"]["assertions_total"] == 2
    assert len(report["groups"][0]["assertions"]) == 2
    assert "debug_group_runs" not in report


def test_debug_group_responses_exclude_request_prompts(document_client) -> None:
    client, session = document_client
    client.app.dependency_overrides[get_runtime_settings] = lambda: Settings(
        _env_file=None,
        app_env="test",
        debug_mode=True,
    )
    report = client.get(f"/v1/analyses/{session.run.id}/document").json()
    assert report["debug_group_runs"][0]["judge_attempts"][0]["raw_response"]
    assert all(
        "group_input" not in run and "validation_input" not in run
        for run in report["debug_group_runs"]
    )


@pytest.mark.parametrize("state", ["missing", "expired"])
def test_document_endpoint_honors_analysis_retention(document_client, state: str) -> None:
    client, session = document_client
    identifier = uuid4() if state == "missing" else session.run.id
    if state == "expired":
        session.run.purge_after = datetime.now(UTC) - timedelta(seconds=1)
    response = client.get(f"/v1/analyses/{identifier}/document")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "analysis_not_found"


def test_tampered_document_audit_is_unavailable_not_a_truth_result(document_client) -> None:
    client, session = document_client
    session.rows[0].snapshot_json["status"] = "tampered"
    assert session.rows[0].snapshot_hash != canonical_document_hash(session.rows[0].snapshot_json)
    response = client.get(f"/v1/analyses/{session.run.id}/document")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "document_audit_invalid"


def test_unqualified_document_cannot_escape_production_gate(document_client) -> None:
    client, session = document_client
    client.app.dependency_overrides[get_runtime_settings] = lambda: Settings(
        _env_file=None,
        app_env="production",
        debug_mode=False,
    )
    response = client.get(f"/v1/analyses/{session.run.id}/document")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "report_not_qualified"


def test_document_submission_queues_exact_full_text_without_synchronous_calls(
    document_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session = document_client
    captured = []
    monkeypatch.setattr(
        analyses,
        "start_analysis",
        lambda *_args, **_kwargs: (
            SimpleNamespace(
                id=session.run.id,
                status="queued",
                stage="queued",
                claim_count=0,
                completed_claims=0,
            ),
            True,
        ),
    )
    monkeypatch.setattr(
        analyses,
        "run_background",
        lambda _id, request, _settings: captured.append(request.input.text),
    )
    text = "Study Alpha " + "complete source context " * 20 + ". It reported outcome Y."
    response = client.post(
        "/v1/analyses",
        json={
            "input": {"type": "text", "text": text},
            "consent": {"privacy_notice_version": "fixture", "accepted": True},
        },
    )
    assert response.status_code == 202
    assert captured == [text]
