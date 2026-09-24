"""Private raw-upload storage adapters."""

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID

from app.core.errors import ExternalCapabilityError


@dataclass(frozen=True, slots=True)
class LocalFilesystemUploadStorage:
    """Development storage for sanitized raw screenshots.

    This adapter deliberately stores only re-encoded image bytes supplied by the
    ingestion service. A production object-storage adapter belongs behind the
    same small interface; raw screenshots must never be placed in PostgreSQL.
    """

    root: Path
    service_name: str = "local_filesystem_upload_storage"

    def __post_init__(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    async def put(self, *, upload_id: UUID, content: bytes) -> str:
        """Persist one private image with an opaque server-generated key."""

        key = f"{upload_id}.png"
        path = self._resolve(key)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as exc:
            raise ExternalCapabilityError(
                code="upload_storage_unavailable",
                message="Screenshot storage is temporarily unavailable.",
            ) from exc

        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            path.unlink(missing_ok=True)
            raise ExternalCapabilityError(
                code="upload_storage_unavailable",
                message="Screenshot storage is temporarily unavailable.",
            ) from exc
        return key

    async def get(self, *, object_key: str) -> bytes:
        """Read a previously sanitized upload without exposing a filesystem path."""

        try:
            return self._resolve(object_key).read_bytes()
        except OSError as exc:
            raise ExternalCapabilityError(
                code="upload_not_available",
                message="The screenshot is no longer available for processing.",
            ) from exc

    async def delete(self, *, object_key: str) -> None:
        """Remove an expired raw upload; deletion is intentionally idempotent."""

        try:
            self._resolve(object_key).unlink(missing_ok=True)
        except OSError as exc:
            raise ExternalCapabilityError(
                code="upload_storage_unavailable",
                message="Screenshot storage is temporarily unavailable.",
            ) from exc

    def _resolve(self, object_key: str) -> Path:
        """Constrain opaque keys to one private directory before file access."""

        candidate = PurePosixPath(object_key)
        if candidate.is_absolute() or len(candidate.parts) != 1 or candidate.name != object_key:
            raise ExternalCapabilityError(
                code="upload_storage_invalid_key",
                message="Screenshot storage could not process the upload.",
            )
        path = (self.root / candidate.name).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ExternalCapabilityError(
                code="upload_storage_invalid_key",
                message="Screenshot storage could not process the upload.",
            ) from exc
        return path
