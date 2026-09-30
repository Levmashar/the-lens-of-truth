"""Small, retrieval-only lay-word variants; never medical entity mappings.

These variants increase source recall. They do not change a claim, establish
clinical equivalence, or provide evidence of any effect. The source wording
remains in the frozen claim snapshot and each expanded query records its origin.
"""

import re

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_LAY_VARIANTS: dict[str, tuple[str, ...]] = {
    "eyesight": ("vision", "sight", "seeing"),
}


def lay_variants(value: str | None) -> tuple[tuple[str, str], ...]:
    """Return bounded (source word, search-only variant) pairs."""

    if not value:
        return ()
    words = {match.group().casefold() for match in _WORD.finditer(value)}
    return tuple(
        (word, variant)
        for word in sorted(words)
        for variant in _LAY_VARIANTS.get(word, ())
    )[:3]
