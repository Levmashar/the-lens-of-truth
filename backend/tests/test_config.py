import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_parse_comma_separated_cors_origins() -> None:
    settings = Settings(
        app_env="test",
        cors_origins_raw="http://localhost:5173, https://lens.example.org ",
    )

    assert settings.cors_origins == ["http://localhost:5173", "https://lens.example.org"]


def test_ncbi_contact_and_tool_require_valid_shape() -> None:
    with pytest.raises(ValidationError):
        Settings(ncbi_email="not-an-email")
    with pytest.raises(ValidationError):
        Settings(ncbi_tool="has spaces")
