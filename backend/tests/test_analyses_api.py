from uuid import UUID

from fastapi.testclient import TestClient


def _submission_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "client": "web",
        "lang": "auto",
        "input": {"type": "text", "text": "A public health claim."},
        "consent": {"privacy_notice_version": "2026-09-01", "accepted": True},
    }


def test_create_analysis_returns_explicit_mock_lifecycle(client: TestClient) -> None:
    response = client.post("/v1/analyses", json=_submission_payload())

    assert response.status_code == 202
    body = response.json()
    assert UUID(body["analysis_id"])
    assert body["status"] == "processing"
    assert body["is_mock"] is True


def test_get_analysis_returns_empty_mock_claims(client: TestClient) -> None:
    analysis_id = "a59b257c-261a-4f6c-a2fc-6a80d4dfad41"
    response = client.get(f"/v1/analyses/{analysis_id}")

    assert response.status_code == 200
    assert response.json()["analysis_id"] == analysis_id
    assert response.json()["claims"] == []
    assert response.json()["is_mock"] is True


def test_analysis_events_use_sse_and_identify_mock_events(client: TestClient) -> None:
    response = client.get("/v1/analyses/a59b257c-261a-4f6c-a2fc-6a80d4dfad41/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: stage" in response.text
    assert '"mock": true' in response.text
    assert "event: completed" in response.text


def test_rejects_submission_without_accepted_consent(client: TestClient) -> None:
    payload = _submission_payload()
    payload["consent"] = {"privacy_notice_version": "2026-09-01", "accepted": False}

    response = client.post("/v1/analyses", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_failed"
