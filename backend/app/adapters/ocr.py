"""OCR adapter backed by the local Tesseract command-line process."""

import asyncio
import csv
import io
from dataclasses import dataclass

from app.core.errors import ExternalCapabilityError


@dataclass(frozen=True, slots=True)
class OcrLine:
    """One recognized line and its normalized confidence score."""

    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class OcrResult:
    """OCR output passed to redaction; it is not persisted as raw text."""

    text: str
    confidence: float | None
    language_used: str
    lines: tuple[OcrLine, ...]


@dataclass(frozen=True, slots=True)
class TesseractOcrAdapter:
    """Use a bounded local OCR process without shell interpolation or network I/O."""

    executable: str
    timeout_seconds: float
    service_name: str = "tesseract"

    async def recognize(self, *, image: bytes, language_hint: str) -> OcrResult:
        """Recognize a sanitized PNG and return only text/confidence metadata."""

        language = _tesseract_language(language_hint)
        try:
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "stdin",
                "stdout",
                "-l",
                language,
                "--psm",
                "6",
                "tsv",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise ExternalCapabilityError(
                code="ocr_unavailable",
                message="Screenshot OCR is not available in this environment.",
            ) from exc

        try:
            stdout, _ = await asyncio.wait_for(process.communicate(image), self.timeout_seconds)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise ExternalCapabilityError(
                code="ocr_timeout",
                message="Screenshot OCR timed out. Please try a smaller, clearer image.",
            ) from exc

        if process.returncode != 0:
            raise ExternalCapabilityError(
                code="ocr_failed",
                message="Screenshot text could not be read. Please try a clearer image.",
                status_code=422,
            )
        return parse_tesseract_tsv(stdout.decode("utf-8", errors="replace"), language)


def parse_tesseract_tsv(payload: str, language_used: str) -> OcrResult:
    """Parse Tesseract TSV without retaining unneeded word-level raw payloads."""

    reader = csv.DictReader(io.StringIO(payload), delimiter="\t")
    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for row in reader:
        word = row.get("text", "").strip()
        confidence = _parse_confidence(row.get("conf", ""))
        if not word or confidence is None:
            continue
        key = (
            str(row.get("page_num", "0")),
            str(row.get("block_num", "0")),
            str(row.get("par_num", "0")),
            str(row.get("line_num", "0")),
        )
        grouped.setdefault(key, []).append(row)

    lines: list[OcrLine] = []
    for words in grouped.values():
        confidences = [_parse_confidence(word["conf"]) for word in words]
        valid_confidences = [value for value in confidences if value is not None]
        lefts = [int(word.get("left", "0")) for word in words]
        tops = [int(word.get("top", "0")) for word in words]
        rights = [
            left + int(word.get("width", "0")) for left, word in zip(lefts, words, strict=True)
        ]
        bottoms = [
            top + int(word.get("height", "0")) for top, word in zip(tops, words, strict=True)
        ]
        lines.append(
            OcrLine(
                text=" ".join(word["text"].strip() for word in words),
                confidence=sum(valid_confidences) / len(valid_confidences),
                left=min(lefts),
                top=min(tops),
                width=max(rights) - min(lefts),
                height=max(bottoms) - min(tops),
            )
        )

    full_text = "\n".join(line.text for line in lines)
    overall_confidence = sum(line.confidence for line in lines) / len(lines) if lines else None
    return OcrResult(
        text=full_text,
        confidence=overall_confidence,
        language_used=language_used,
        lines=tuple(lines),
    )


def _parse_confidence(value: str) -> float | None:
    try:
        confidence = float(value)
    except ValueError:
        return None
    return confidence / 100 if confidence >= 0 else None


def _tesseract_language(language_hint: str) -> str:
    normalized = language_hint.lower()
    if normalized in {"zh", "zh-cn", "zh_hans"}:
        return "chi_sim+eng"
    if normalized in {"zh-tw", "zh-hk", "zh_hant"}:
        return "chi_tra+eng"
    if normalized.startswith("en"):
        return "eng"
    return "eng+chi_sim+chi_tra"
