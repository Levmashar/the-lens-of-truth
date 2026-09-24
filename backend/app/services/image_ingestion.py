"""Decode, validate, and re-encode screenshots before private storage."""

import hashlib
import io
from dataclasses import dataclass

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.errors import UploadValidationError

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


@dataclass(frozen=True, slots=True)
class SanitizedImage:
    """Metadata and safe PNG bytes produced after server-side validation."""

    content: bytes
    media_type: str
    content_sha256: str
    width: int
    height: int

    @property
    def byte_count(self) -> int:
        """Return the length of the re-encoded payload that is actually stored."""

        return len(self.content)


class ScreenshotSanitizer:
    """Reject unsafe images and strip metadata through a clean PNG re-encode."""

    def __init__(self, *, max_bytes: int, max_pixels: int) -> None:
        self._max_bytes = max_bytes
        self._max_pixels = max_pixels

    async def sanitize_upload(self, upload: UploadFile) -> SanitizedImage:
        """Read an upload with a hard byte cap before decoding it."""

        chunks: list[bytes] = []
        total = 0
        try:
            while chunk := await upload.read(64 * 1024):
                total += len(chunk)
                if total > self._max_bytes:
                    raise UploadValidationError(
                        code="screenshot_too_large",
                        message="Screenshot exceeds the allowed file size.",
                        status_code=413,
                    )
                chunks.append(chunk)
        finally:
            await upload.close()
        return self.sanitize_bytes(b"".join(chunks))

    def sanitize_bytes(self, payload: bytes) -> SanitizedImage:
        """Validate decoded pixels, reject animation, and emit metadata-free PNG bytes."""

        if not payload:
            raise UploadValidationError(
                code="empty_screenshot",
                message="Screenshot upload is empty.",
            )
        if len(payload) > self._max_bytes:
            raise UploadValidationError(
                code="screenshot_too_large",
                message="Screenshot exceeds the allowed file size.",
                status_code=413,
            )
        try:
            with Image.open(io.BytesIO(payload)) as source:
                image_format = source.format
                width, height = source.size
                if image_format not in ALLOWED_IMAGE_FORMATS:
                    raise UploadValidationError(
                        code="unsupported_screenshot_format",
                        message="Upload a PNG, JPEG, or WebP screenshot.",
                    )
                if getattr(source, "n_frames", 1) != 1:
                    raise UploadValidationError(
                        code="animated_screenshot_not_allowed",
                        message="Upload a single-frame screenshot.",
                    )
                if width <= 0 or height <= 0 or width * height > self._max_pixels:
                    raise UploadValidationError(
                        code="screenshot_dimensions_not_allowed",
                        message="Screenshot dimensions exceed the allowed limit.",
                    )
                source.verify()

            with Image.open(io.BytesIO(payload)) as decoded:
                normalized = ImageOps.exif_transpose(decoded).convert("RGB")
                output = io.BytesIO()
                normalized.save(output, format="PNG", optimize=True)
        except UploadValidationError:
            raise
        except (Image.DecompressionBombError, OSError, UnidentifiedImageError) as exc:
            raise UploadValidationError(
                code="invalid_screenshot",
                message="Screenshot could not be safely decoded.",
            ) from exc

        content = output.getvalue()
        if len(content) > self._max_bytes:
            raise UploadValidationError(
                code="sanitized_screenshot_too_large",
                message="Screenshot is too large after safety processing.",
                status_code=413,
            )
        return SanitizedImage(
            content=content,
            media_type="image/png",
            content_sha256=hashlib.sha256(content).hexdigest(),
            width=width,
            height=height,
        )
