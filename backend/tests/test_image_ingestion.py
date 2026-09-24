from io import BytesIO

import pytest
from PIL import Image

from app.core.errors import UploadValidationError
from app.services.image_ingestion import ScreenshotSanitizer


def _image_bytes(*, image_format: str, size: tuple[int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "white").save(output, format=image_format)
    return output.getvalue()


def test_sanitizer_sniffs_and_reencodes_supported_images_to_png() -> None:
    sanitizer = ScreenshotSanitizer(max_bytes=1_000_000, max_pixels=100)

    image = sanitizer.sanitize_bytes(_image_bytes(image_format="JPEG", size=(4, 3)))

    assert image.media_type == "image/png"
    assert image.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert image.width == 4
    assert image.height == 3
    assert len(image.content_sha256) == 64


def test_sanitizer_rejects_non_image_content() -> None:
    sanitizer = ScreenshotSanitizer(max_bytes=1_000_000, max_pixels=100)

    with pytest.raises(UploadValidationError, match="safely decoded"):
        sanitizer.sanitize_bytes(b"not an image")


def test_sanitizer_rejects_images_over_pixel_limit() -> None:
    sanitizer = ScreenshotSanitizer(max_bytes=1_000_000, max_pixels=4)

    with pytest.raises(UploadValidationError, match="dimensions"):
        sanitizer.sanitize_bytes(_image_bytes(image_format="PNG", size=(3, 2)))
