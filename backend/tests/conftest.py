import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def isolate_model_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compose credentials must never select live models in offline tests.

    Preserve DATABASE_URL/RUN_DB_TESTS for explicitly enabled PostgreSQL tests.
    Individual tests can still configure providers with monkeypatch or Settings.
    """
    for name in tuple(os.environ):
        if name.startswith(("JUDGE_", "CLAIM_EXTRACTOR_", "VALIDATOR_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("AUTHORITATIVE_ENABLED", "false")


@pytest.fixture
def client() -> Generator[TestClient]:
    settings = Settings(app_env="test", cors_origins_raw="http://localhost:5173")
    with TestClient(create_app(settings)) as test_client:
        yield test_client
