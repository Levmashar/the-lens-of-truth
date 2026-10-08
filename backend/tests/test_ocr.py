import asyncio
import io
import shutil
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.adapters.ocr import TesseractOcrAdapter, parse_tesseract_tsv
from app.core.errors import ExternalCapabilityError
from app.services.image_ingestion import ScreenshotSanitizer


def test_tesseract_tsv_parser_returns_lines_and_normalized_confidence() -> None:
    payload = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t10\t20\t30\t12\t90.0\tVitamin",
            "5\t1\t1\t1\t1\t2\t45\t20\t20\t12\t80.0\tC",
        ]
    )

    result = parse_tesseract_tsv(payload, "eng")

    assert result.text == "Vitamin C"
    assert result.confidence == pytest.approx(0.85)
    assert result.lines[0].width == 55


def test_ocr_preserves_literal_quotes_without_swallowing_other_rows() -> None:
    payload = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        '5\t1\t1\t1\t1\t1\t0\t0\t20\t10\t90\t"Smoking\n'
        "5\t1\t1\t1\t1\t2\t25\t0\t20\t10\t90\tcauses\n"
        '5\t1\t1\t1\t1\t3\t50\t0\t20\t10\t90\tcancer."\n'
    )

    assert parse_tesseract_tsv(payload, "eng").text == '"Smoking causes cancer."'


def test_ocr_uses_automatic_layout_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    process = Mock(returncode=0)
    process.communicate = AsyncMock(return_value=(b"", b""))
    start = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", start)

    asyncio.run(TesseractOcrAdapter("tesseract", 20).recognize(image=b"png", language_hint="en"))

    assert start.call_args.args == (
        "tesseract",
        "stdin",
        "stdout",
        "-l",
        "eng",
        "--psm",
        "3",
        "tsv",
    )
    process.communicate.assert_awaited_once_with(b"png")


@pytest.mark.parametrize("failure", [FileNotFoundError, PermissionError, NotImplementedError])
def test_ocr_start_failure_is_a_safe_capability_error(
    monkeypatch: pytest.MonkeyPatch,
    failure: type[Exception],
) -> None:
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=failure()))

    with pytest.raises(ExternalCapabilityError) as caught:
        asyncio.run(
            TesseractOcrAdapter("private/path", 20).recognize(image=b"png", language_hint="en")
        )

    assert caught.value.code == "ocr_unavailable"
    assert "private/path" not in str(caught.value)


@pytest.mark.parametrize("failure", [TimeoutError, asyncio.CancelledError])
def test_ocr_reaps_child_and_drains_output_on_timeout_or_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    failure: type[BaseException],
) -> None:
    process = Mock(returncode=None)
    process.communicate = AsyncMock(side_effect=[failure(), (b"", b"")])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    expected = (
        asyncio.CancelledError if failure is asyncio.CancelledError else ExternalCapabilityError
    )

    with pytest.raises(expected):
        asyncio.run(
            TesseractOcrAdapter("tesseract", 20).recognize(image=b"png", language_hint="en")
        )

    process.kill.assert_called_once()
    assert process.communicate.await_count == 2


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Local OCR engine not installed")
@pytest.mark.parametrize(
    "image_format,background",
    [
        ("PNG", "white"),
        ("JPEG", "white"),
        ("WEBP", "white"),
        ("PNG", "transparent"),
        ("PNG", "black"),
    ],
)
def test_real_local_ocr_reads_sanitized_screenshot_variants(
    image_format: str,
    background: str,
) -> None:
    source = Image.new(
        "RGBA", (640, 110), (0, 0, 0, 0) if background == "transparent" else background
    )
    ImageDraw.Draw(source).text(
        (20, 25),
        '"Smoking causes lung cancer."',
        font=ImageFont.load_default(size=30),
        fill="white" if background == "black" else "black",
    )
    output = io.BytesIO()
    if image_format == "JPEG":
        source.convert("RGB").save(output, image_format)
    else:
        source.save(output, image_format)
    image = ScreenshotSanitizer(max_bytes=1_000_000, max_pixels=1_000_000).sanitize_bytes(
        output.getvalue(),
    )

    result = asyncio.run(
        TesseractOcrAdapter("tesseract", 20).recognize(
            image=image.content,
            language_hint="en",
        )
    )

    assert "Smoking causes lung cancer." in result.text
    assert result.confidence is not None
