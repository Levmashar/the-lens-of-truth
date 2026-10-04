from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_healthcheck_returns_liveness_and_request_id(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["environment"] == "test"
    assert UUID(response.headers["X-Request-ID"])
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_unknown_route_uses_safe_error_envelope(client: TestClient) -> None:
    response = client.get("/not-a-route")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_debug_mode_is_explicit_and_never_enabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Exercise debug gating, not live-database restart reconciliation or retention.
    # A development/production TestClient must not interrupt another API process.
    monkeypatch.setattr("app.main._mark_interrupted", lambda: 0)
    monkeypatch.setattr("app.main._purge_expired", lambda _settings: 0)
    development = Settings(_env_file=None, app_env="development", debug_mode=True)
    production = Settings(_env_file=None, app_env="production", debug_mode=True)
    disabled = Settings(_env_file=None, app_env="development", debug_mode=False)

    assert development.debug_enabled
    assert not production.debug_enabled
    assert not disabled.debug_enabled
    with TestClient(create_app(development)) as app:
        assert app.get("/healthz").json()["debug_enabled"] is True
    with TestClient(create_app(production)) as app:
        assert app.get("/healthz").json()["debug_enabled"] is False
