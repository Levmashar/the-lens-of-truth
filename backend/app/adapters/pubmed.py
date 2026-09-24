"""Official NCBI E-utilities adapter with bounded requests and optional Redis cache."""

import asyncio
import hashlib
import json
import logging
import time
from typing import Protocol

import httpx

from app.retrieval.errors import RetrievalError, RetrievalFailureKind
from app.retrieval.models import PubMedDocument
from app.retrieval.normalize import parse_pubmed_xml

logger = logging.getLogger(__name__)
_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
_VERSION = "pubmed-eutils-1"
_THROTTLE_LOCK = asyncio.Lock()
_LAST_REQUEST = 0.0


class QueryCache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


class RedisQueryCache:
    """Best-effort Redis cache; its failure never changes PubMed results."""

    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis

        self._client: Redis = Redis.from_url(url, decode_responses=True,
                                              socket_timeout=1, socket_connect_timeout=1)

    async def get(self, key: str) -> str | None:
        try:
            value = await self._client.get(key)
            return value if isinstance(value, str) else None
        except Exception:
            logger.warning("PubMed query cache read unavailable")
            return None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            await self._client.set(key, value, ex=ttl_seconds)
        except Exception:
            logger.warning("PubMed query cache write unavailable")


class PubMedAdapter:
    """Search PubMed and fetch XML metadata only, never HTML or arbitrary URLs."""

    service_name = "pubmed_eutils"

    def __init__(
        self, *, tool: str, email: str, api_key: str | None = None,
        timeout_seconds: float = 12, max_retries: int = 1,
        minimum_interval_seconds: float = 0.36, retmax: int = 10,
        cache: QueryCache | None = None, cache_ttl_seconds: int = 21_600,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._tool = tool
        self._email = email
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._minimum_interval = minimum_interval_seconds
        self._retmax = retmax
        self._cache = cache
        self._cache_ttl = cache_ttl_seconds
        self._client = client

    async def search(self, query: str) -> tuple[tuple[str, ...], bool]:
        """Return PMIDs and whether the result came from the optional cache."""

        normalized = " ".join(query.split())
        digest = hashlib.sha256(
            f"pubmed|{_VERSION}|relevance|{self._retmax}|{normalized}".encode()
        ).hexdigest()
        cache_key = f"pubmed:esearch:{digest}"
        if self._cache is not None:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                try:
                    parsed = json.loads(cached)
                    if isinstance(parsed, list) and all(
                        isinstance(item, str) and item.isdigit() for item in parsed
                    ):
                        return tuple(parsed), True
                except (ValueError, TypeError):
                    pass
        response = await self._request("esearch.fcgi", {
            "db": "pubmed", "term": normalized, "retmode": "json",
            "retmax": str(self._retmax), "sort": "relevance",
        })
        try:
            data = response.json()
            if isinstance(data, dict) and "error" in data:
                error_message = str(data["error"]).casefold()
                if "rate limit" in error_message:
                    raise RetrievalError("rate_limited")
                raise RetrievalError("upstream_http")
            ids = data["esearchresult"]["idlist"]
            if not isinstance(ids, list) or not all(
                isinstance(item, str) and item.isdigit() for item in ids
            ):
                raise ValueError("Invalid PMID list")
        except (ValueError, KeyError, TypeError) as exc:
            raise RetrievalError("malformed_response") from exc
        if self._cache is not None:
            await self._cache.set(cache_key, json.dumps(ids), self._cache_ttl)
        return tuple(ids), False

    async def fetch(self, pmids: tuple[str, ...]) -> tuple[PubMedDocument, ...]:
        """Fetch one bounded batch; no results is a valid empty return."""

        if not pmids:
            return ()
        if len(pmids) > 50 or any(not value.isdigit() for value in pmids):
            raise ValueError("EFetch accepts at most 50 numeric PMIDs")
        response = await self._request("efetch.fcgi", {
            "db": "pubmed", "id": ",".join(pmids), "retmode": "xml",
        })
        return parse_pubmed_xml(response.content)

    async def _request(self, endpoint: str, params: dict[str, str]) -> httpx.Response:
        global _LAST_REQUEST
        safe_params = {**params, "tool": self._tool, "email": self._email}
        if self._api_key:
            safe_params["api_key"] = self._api_key
        for attempt in range(self._max_retries + 1):
            async with _THROTTLE_LOCK:
                remaining = self._minimum_interval - (time.monotonic() - _LAST_REQUEST)
                if remaining > 0:
                    await asyncio.sleep(remaining)
                _LAST_REQUEST = time.monotonic()
            try:
                if self._client is None:
                    async with httpx.AsyncClient(
                        base_url=_BASE_URL, timeout=self._timeout,
                        headers={"User-Agent": f"{self._tool}/1.0 ({self._email})"},
                    ) as client:
                        async with asyncio.timeout(self._timeout):
                            response = await client.get(endpoint, params=safe_params)
                else:
                    async with asyncio.timeout(self._timeout):
                        response = await self._client.get(endpoint, params=safe_params,
                                                          timeout=self._timeout,
                                                          headers={"User-Agent": (
                                                              f"{self._tool}/1.0 ({self._email})"
                                                          )})
            except (httpx.TimeoutException, TimeoutError) as exc:
                kind: RetrievalFailureKind = "timeout"
                last_error: Exception = exc
            except httpx.TransportError as exc:
                kind = "transport"
                last_error = exc
            else:
                if len(response.content) > 4_000_000:
                    raise RetrievalError("malformed_response")
                if response.status_code == 429:
                    kind = "rate_limited"
                elif response.status_code >= 500:
                    kind = "upstream_http"
                elif response.status_code >= 400:
                    raise RetrievalError("upstream_http")
                else:
                    return response
                last_error = RetrievalError(kind)
            if attempt == self._max_retries:
                logger.warning("PubMed request failed", extra={
                    "failure_type": kind, "attempt_number": attempt + 1,
                    "endpoint": endpoint,
                })
                raise RetrievalError(kind) from last_error
            await asyncio.sleep(min(0.5 * (2 ** attempt), 2.0))
        raise AssertionError("Unreachable retry state")
