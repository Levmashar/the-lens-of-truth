"""Conservative local PII redaction before any model-bound processing."""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RedactionMatch:
    """One position-preserving redaction, without retaining the matched value."""

    start: int
    end: int
    category: str


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Sanitized text and metadata needed for safe audit metrics."""

    text: str
    matches: tuple[RedactionMatch, ...]


class PiiRedactor:
    """Redact high-confidence identifier patterns while retaining source offsets.

    This baseline is deliberately conservative and only detects structured PII.
    It does not claim to identify names, diagnoses, or every jurisdiction's
    identifier format; those require an approved later capability.
    """

    _patterns: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("email", re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.+-])")),
        (
            "phone",
            re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{6,}\d)(?!\w)"),
        ),
        ("us_ssn", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
        (
            "china_national_id",
            re.compile(r"(?<![0-9A-Za-z])\d{17}[0-9Xx](?![0-9A-Za-z])"),
        ),
        (
            "medical_record_number",
            re.compile(
                r"(?i)\b(?:mrn|medical[ -]?record(?:[ -]?number)?|patient[ -]?id)"
                r"\s*[:#-]?\s*[A-Z0-9-]{5,}\b"
            ),
        ),
        ("payment_card", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")),
    )

    def redact(self, text: str) -> RedactionResult:
        """Replace each matched character with a fixed-width mask character."""

        matches = self._non_overlapping_matches(text)
        masked = list(text)
        for match in matches:
            for index in range(match.start, match.end):
                masked[index] = "█"
        return RedactionResult(text="".join(masked), matches=tuple(matches))

    def _non_overlapping_matches(self, text: str) -> list[RedactionMatch]:
        candidates: list[RedactionMatch] = []
        for category, pattern in self._patterns:
            candidates.extend(
                RedactionMatch(match.start(), match.end(), category)
                for match in pattern.finditer(text)
            )
        candidates.sort(key=lambda match: (match.start, -(match.end - match.start)))

        accepted: list[RedactionMatch] = []
        current_end = -1
        for candidate in candidates:
            if candidate.start >= current_end:
                accepted.append(candidate)
                current_end = candidate.end
        return accepted
