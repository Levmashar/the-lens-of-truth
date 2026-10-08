"""Passive, task-local public-source HTTP attempt counts without request content."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

SourceProvider = Literal["pubmed", "pmc", "crossref", "authoritative"]
SourceOperation = Literal["search", "fetch", "link", "work", "document"]
_ALLOWED = frozenset({
    ("pubmed", "search"), ("pubmed", "fetch"), ("pubmed", "link"),
    ("pmc", "search"), ("pmc", "fetch"), ("pmc", "link"),
    ("crossref", "work"), ("authoritative", "document"),
})
_ACTIVE: ContextVar[dict[str, int] | None] = ContextVar("source_http_counts", default=None)


@contextmanager
def source_http_metrics() -> Iterator[dict[str, int]]:
    """Scope counts to one group; concurrent child tasks share only its counters."""
    counts: dict[str, int] = {}
    token = _ACTIVE.set(counts)
    try:
        yield counts
    finally:
        _ACTIVE.reset(token)


def record_source_http(provider: SourceProvider, operation: SourceOperation) -> None:
    """Count immediately before a leaf HTTP send, including retries/failures.

    Outside a scope this is a no-op. Only fixed provider/operation constants
    enter the dictionary; URLs, queries, identifiers and credentials cannot.
    """
    counts = _ACTIVE.get()
    if counts is not None and (provider, operation) in _ALLOWED:
        key = f"{provider}.{operation}"
        counts[key] = counts.get(key, 0) + 1


def record_ncbi_source_http(
    endpoint: str, *, database: str | None, source_database: str | None = None,
) -> None:
    """Translate approved E-utilities operation names into content-free constants."""
    operation: SourceOperation
    if endpoint == "esearch.fcgi":
        operation = "search"
    elif endpoint == "efetch.fcgi":
        operation = "fetch"
    elif endpoint == "elink.fcgi":
        operation = "link"
    else:
        return
    if database == "pmc" or source_database == "pmc":
        record_source_http("pmc", operation)
    elif database == "pubmed" or source_database == "pubmed":
        record_source_http("pubmed", operation)
