"""Redact credentials from developer-only diagnostic artifacts."""

import re
from collections.abc import Mapping
from typing import Any

from pydantic import SecretStr


def diagnostic_secrets(settings: object) -> tuple[str, ...]:
    return tuple(value.get_secret_value() for value in vars(settings).values()
                 if isinstance(value, SecretStr) and value.get_secret_value())


def sanitize_diagnostic(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, str):
        for secret in sorted((s for s in secrets if s), key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~-]+", "Bearer [REDACTED]", value)
        return re.sub(
            r"(?i)(\b(?:api[_-]?key|api[_-]?token|authorization|password)"
            r"[\"']?\s*[:=]\s*)[\"']?[^\s,}\"']+", r"\1[REDACTED]", value,
        )
    if isinstance(value, Mapping):
        return {key: "[REDACTED]" if str(key).casefold() in {
            "api_key", "api_token", "authorization", "password",
        } else sanitize_diagnostic(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_diagnostic(item, secrets) for item in value]
    return value
