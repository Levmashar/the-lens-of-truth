"""Exclusive, sanitized runtime artifacts with explicit retention boundaries."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.diagnostics import diagnostic_secrets, sanitize_diagnostic


def runtime_directory(path: Path) -> Path:
    directory = path.resolve()
    source = Path(__file__).resolve()
    allowed = {source.parents[3] / "runtime", source.parents[2] / "runtime"}
    if directory not in allowed:
        raise ValueError("Use an ignored runtime directory")
    result = directory / "bakeoff"
    result.mkdir(parents=True, exist_ok=True)
    return result


def save_artifact(directory: Path, prefix: str, data: dict[str, Any], settings: Settings) -> Path:
    path = directory / f"{prefix}-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(sanitize_diagnostic(data, diagnostic_secrets(settings)), handle,
                  ensure_ascii=False, indent=2, default=str)
    return path


def load_retained(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    expiry = data.get("purge_after")
    if not expiry or datetime.fromisoformat(expiry) <= datetime.now(UTC):
        raise ValueError("Expired or unbounded capture; do not recover or extend retention")
    return data
