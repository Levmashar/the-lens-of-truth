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


@pytest.mark.parametrize("image_format", ["PNG", "WEBP"])
def test_transparent_screenshot_is_flattened_on_white(image_format: str) -> None:
    source = Image.new("RGBA", (4, 3), (0, 0, 0, 0))
    source.putpixel((1, 1), (0, 0, 0, 255))
    output = BytesIO()
    source.save(output, format=image_format, lossless=True)

    image = ScreenshotSanitizer(max_bytes=1_000_000, max_pixels=100).sanitize_bytes(
        output.getvalue(),
    )

    with Image.open(BytesIO(image.content)) as sanitized:
        assert sanitized.getpixel((0, 0)) == (255, 255, 255)
        assert sanitized.getpixel((1, 1)) == (0, 0, 0)


def test_sanitizer_reports_oriented_dimensions_and_strips_metadata() -> None:
    source = Image.new("RGB", (4, 3), "white")
    exif = source.getexif()
    exif[274] = 6
    exif[315] = "Private author"
    output = BytesIO()
    source.save(output, format="JPEG", exif=exif)

    image = ScreenshotSanitizer(max_bytes=1_000_000, max_pixels=100).sanitize_bytes(
        output.getvalue(),
    )

    assert (image.width, image.height) == (3, 4)
    with Image.open(BytesIO(image.content)) as sanitized:
        assert sanitized.size == (3, 4)
        assert not sanitized.getexif()
