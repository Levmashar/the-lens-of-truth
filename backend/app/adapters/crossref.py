"""Bounded Crossref DOI metadata enrichment; never a medical search adapter."""

import asyncio
import hashlib
import logging
import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.adapters.pubmed import QueryCache
from app.retrieval.models import (
    CrossrefEnrichment,
    IntegrityCheck,
    IntegrityReference,
    IntegrityStatus,
)

logger = logging.getLogger(__name__)
_VERSION = "crossref-rest-1"
_BASE_URL = "https://api.crossref.org/v1/"
_DOI = re.compile(r"^10\.\d{4,9}/\S{1,450}$", re.IGNORECASE)
_UPDATE_TYPES: dict[str, IntegrityStatus] = {
    "retraction": "retracted", "partial_retraction": "retracted",
    "withdrawal": "retracted", "removal": "retracted",
    "expression_of_concern": "expression_of_concern",
    "correction": "corrected", "corrigendum": "corrected", "erratum": "corrected",
    "new_version": "updated", "new_edition": "updated", "addendum": "updated",
    "clarification": "updated",
}
_RELATIONS: dict[str, IntegrityStatus] = {
    "is-retracted-by": "retracted", "is-corrected-by": "corrected",
    "is-updated-by": "updated", "has-expression-of-concern": "expression_of_concern",
}


class CrossrefDoiMismatch(ValueError):
    """The returned work cannot safely be attached to the requested DOI."""


def _date(value: object) -> date | None:
    if not isinstance(value, dict):
        return None
    parts = value.get("date-parts")
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
        return None
    values = parts[0]
    if not values or not all(isinstance(part, int) for part in values[:3]):
        return None
    try:
        return date(values[0], values[1] if len(values) > 1 else 1,
                    values[2] if len(values) > 2 else 1)
    except ValueError:
        return None


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _references(message: dict[str, Any]) -> tuple[IntegrityReference, ...]:
    references: list[IntegrityReference] = []
    for field in ("updated-by", "update-to"):
        items = message.get(field, [])
        if not isinstance(items, list):
            raise ValueError("Invalid Crossref update list")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Invalid Crossref update")
            related = _string(item.get("DOI"))
            update_type = _string(item.get("type"))
            if related is None or update_type is None or not _DOI.fullmatch(related):
                raise ValueError("Invalid Crossref update reference")
            # update-to describes a notice's target. It must not label the
            # notice itself as retracted. updated-by describes this work.
            signal = (
                _UPDATE_TYPES.get(update_type.casefold(), "updated")
                if field == "updated-by" else None
            )
            references.append(IntegrityReference(
                source="crossref", relation=f"{field}:{update_type.casefold()}",
                identifier=related, identifier_type="doi", signal=signal,
                assertion_source=_string(item.get("source")),
            ))
    relations = message.get("relation", {})
    if not isinstance(relations, dict):
        raise ValueError("Invalid Crossref relations")
    for relation, items in relations.items():
        if not isinstance(items, list):
            raise ValueError("Invalid Crossref relation list")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Invalid Crossref relation")
            related = _string(item.get("id"))
            if related is None or not _DOI.fullmatch(related):
                continue  # Non-DOI relationship identifiers are outside this contract.
            references.append(IntegrityReference(
                source="crossref", relation=str(relation), identifier=related,
                identifier_type="doi", signal=_RELATIONS.get(str(relation).casefold()),
            ))
    return tuple(references)


def parse_crossref_work(message: object, doi: str, checked_at: datetime) -> CrossrefEnrichment:
    if not isinstance(message, dict):
        raise ValueError("Invalid Crossref work")
    returned_doi = _string(message.get("DOI"))
    if returned_doi is None or returned_doi.casefold() != doi.casefold():
        raise CrossrefDoiMismatch("Crossref DOI mismatch")
    for field in ("type", "publisher"):
        if message.get(field) is not None and not isinstance(message[field], str):
            raise ValueError("Invalid Crossref field")
    return CrossrefEnrichment(
        check=IntegrityCheck(source="crossref", status="checked", checked_at=checked_at,
                             version=_VERSION),
        doi=returned_doi, work_type=_string(message.get("type")),
        publisher=_string(message.get("publisher")),
        published_date=_date(message.get("published")) or _date(message.get("issued")),
        deposited_date=_date(message.get("deposited")),
        references=_references(message),
    )


class CrossrefAdapter:
    """Optional polite-pool metadata lookup with short cache and fail-open errors."""

    def __init__(
        self, *, mailto: str, timeout_seconds: float = 8, max_retries: int = 1,
        cache: QueryCache | None = None, cache_ttl_seconds: int = 3600,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._mailto = mailto
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._cache = cache
        self._cache_ttl = cache_ttl_seconds
        self._client = client

    async def enrich(self, doi: str) -> CrossrefEnrichment:
        normalized = doi.strip().casefold()
        now = datetime.now(UTC)
        if not _DOI.fullmatch(normalized):
            return self._failure(doi, "invalid_doi", now)
        digest = hashlib.sha256(f"crossref|{_VERSION}|{normalized}".encode()).hexdigest()
        key = f"crossref:doi:{digest}"
        if self._cache is not None:
            try:
                cached = await self._cache.get(key)
                if cached:
                    value = CrossrefEnrichment.model_validate_json(cached)
                    if value.doi and value.doi.casefold() == normalized:
                        return value
            except Exception:
                logger.warning("Crossref cache read unavailable")
        for attempt in range(self._max_retries + 1):
            failure = "transport"
            retry_after = 0.5
            try:
                response = await self._request(normalized)
                if response.status_code == 404:
                    return CrossrefEnrichment(
                        check=IntegrityCheck(source="crossref", status="not_found",
                                             checked_at=datetime.now(UTC), version=_VERSION),
                        doi=normalized,
                    )
                if response.status_code == 429:
                    failure = "rate_limited"
                    retry_after = self._retry_after(response)
                elif response.status_code >= 500:
                    failure = "upstream_http"
                elif response.status_code >= 400:
                    failure = "upstream_http"
                    break
                else:
                    if len(response.content) > 512_000:
                        return self._failure(normalized, "malformed_response", now)
                    payload = response.json()
                    if not isinstance(payload, dict) or payload.get("status") != "ok":
                        raise ValueError("Invalid Crossref response envelope")
                    result = parse_crossref_work(
                        payload.get("message"), normalized, datetime.now(UTC)
                    )
                    if self._cache is not None:
                        try:
                            await self._cache.set(key, result.model_dump_json(), self._cache_ttl)
                        except Exception:
                            logger.warning("Crossref cache write unavailable")
                    return result
            except (httpx.TimeoutException, TimeoutError):
                failure = "timeout"
            except httpx.TransportError:
                failure = "transport"
            except CrossrefDoiMismatch:
                return self._failure(normalized, "doi_mismatch", now)
            except (ValueError, TypeError):
                return self._failure(normalized, "malformed_response", now)
            if attempt < self._max_retries:
                await asyncio.sleep(min(retry_after, 2.0))
        return self._failure(normalized, failure, now)

    async def _request(self, doi: str) -> httpx.Response:
        path = f"works/{quote(doi, safe='')}"
        headers = {"User-Agent": f"TheLensOfTruth/1.0 (mailto:{self._mailto})"}
        if self._client is None:
            async with httpx.AsyncClient(base_url=_BASE_URL, timeout=self._timeout) as client:
                async with asyncio.timeout(self._timeout):
                    return await client.get(path, params={"mailto": self._mailto},
                                            headers=headers)
        async with asyncio.timeout(self._timeout):
            return await self._client.get(path, params={"mailto": self._mailto},
                                          headers=headers, timeout=self._timeout)

    @staticmethod
    def _retry_after(response: httpx.Response) -> float:
        try:
            return min(max(float(response.headers.get("Retry-After", "0.5")), 0.0), 2.0)
        except ValueError:
            return 0.5

    @staticmethod
    def _failure(doi: str, failure_type: str, checked_at: datetime) -> CrossrefEnrichment:
        logger.warning("Crossref enrichment failed", extra={"failure_type": failure_type})
        return CrossrefEnrichment(
            check=IntegrityCheck(source="crossref", status="failed", checked_at=checked_at,
                                 version=_VERSION, failure_type=failure_type),
            doi=doi,
        )
