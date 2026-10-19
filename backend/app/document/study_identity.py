"""Conservative publication-version clues, independent of evidence qualification."""

import re
from decimal import Decimal

from app.retrieval.models import ClaimSnapshot, PubMedDocument


def _words(text: str) -> set[str]:
    return {w.casefold() for w in re.findall(r"[A-Za-z]+", text) if len(w) > 2} - {
        "the",
        "and",
        "for",
        "with",
        "from",
        "was",
        "were",
    }


def metadata_clues(clues: str, document: PubMedDocument) -> tuple[str, ...]:
    """A title plus publisher/author/year is bibliographic, not topic similarity."""
    normalized = " ".join(re.findall(r"[\w]+", clues.casefold()))
    title = " ".join(re.findall(r"[\w]+", document.title.casefold()))
    if len(_words(title)) < 3 or title not in normalized:
        return ()
    journal_words = _words(document.journal or "") - {
        "the",
        "and",
        "for",
        "journal",
        "review",
        "reviews",
        "systematic",
        "database",
        "international",
        "science",
        "scientific",
        "medicine",
        "medical",
        "clinical",
    }
    publisher = bool(journal_words & _words(clues))
    author = any(
        len(name.split()[-1]) > 3 and name.split()[-1].casefold() in _words(clues)
        for name in document.authors
        if name.split()
    )
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", clues))
    year = bool(document.publication_date and str(document.publication_date.year) in years)
    if not (publisher or author or year):
        return ()
    return ("Exact normalized publication title and independent publication metadata agree.",)


def _percent_signatures(text: str) -> set[tuple[str, str]]:
    # Identity only: literal percentages, never RR-to-percent conversion or rounding.
    # Interval bounds are not primary result fingerprints.
    clean = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", " ", text)
    values = list(re.finditer(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%", clean))
    bindings = list(re.finditer(r"\b(?:in|for|among)\s+(?:the\s+)?([A-Za-z-]+)", clean, re.I))
    signatures = set()
    for index, number in enumerate(values):
        next_start = values[index + 1].start() if index + 1 < len(values) else len(clean)
        following = [
            b
            for b in bindings
            if number.end() <= b.start() < next_start
            and b.start() - number.end() < 45
            and not re.search(r"\band\b|[.;]", clean[number.end() : b.start()], re.I)
        ]
        preceding = [
            b for b in bindings if b.end() <= number.start() and number.start() - b.end() < 100
        ]
        bound = following[0] if following else preceding[-1] if preceding else None
        if bound:
            signatures.add((str(Decimal(number.group(1)).normalize()), bound.group(1).casefold()))
    return signatures


def version_fingerprints(snapshots: dict[str, ClaimSnapshot], source_text: str) -> tuple[str, ...]:
    """Require multiple exact, population-bound numeric findings from owned text.

    Identity does not establish that any claimed inference/effect is correct;
    source attribution, numeric comparability and qualifications still run.
    """
    source = _percent_signatures(source_text)
    matches: set[tuple[str, str]] = set()
    for claim in snapshots.values():
        endpoint = _words(claim.pico.outcome or "") if claim.pico else set()
        if not endpoint or not endpoint & _words(source_text):
            continue
        matches.update(_percent_signatures(claim.raw_text) & source)
    if len(matches) < 2 or len({binding for _, binding in matches}) < 2:
        return ()
    return tuple(
        f"Exact source-grounded result fingerprint: {value}% / {binding}."
        for value, binding in sorted(matches)
    )
