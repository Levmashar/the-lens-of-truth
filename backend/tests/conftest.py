from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client() -> Generator[TestClient]:
    settings = Settings(app_env="test", cors_origins_raw="http://localhost:5173")
    with TestClient(create_app(settings)) as test_client:
        yield test_client
