"""Explicit experimental subjects, never inferred clinical applicability."""

import re


def laboratory_claim(text: str, population: str | None = None) -> bool:
    """Require a named cellular/laboratory subject, not a lab measurement."""
    subject = population or text
    return bool(re.search(r"\b(?:cell[- ]lines?|cell cultures?|cultured cells|in vitro)\b",
                          subject, re.I))
