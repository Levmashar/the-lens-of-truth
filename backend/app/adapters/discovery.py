"""Bounded scholarly discovery. Search records are leads, never clinical evidence.

Only exact identifier matches hydrated from NCBI enter the Evidence Pack. Records
without a verifiable PMID remain visible in diagnostics, not fabricated abstracts.
"""

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, replace
from typing import Any

import httpx

from app.adapters.pubmed import QueryCache
from app.adapters.source_metrics import record_source_http


@dataclass(frozen=True)
class DiscoveryLead:
    provider: str
    identifier: str
    pmid: str | None
    doi: str | None
    title: str
    publication_type: str
    query: str | None = None


class ScholarlyDiscovery:
    def __init__(
        self,
        *,
        cache: QueryCache | None = None,
        client: httpx.AsyncClient | None = None,
        openalex_api_key: str | None = None,
    ) -> None:
        self.cache = cache
        self.client = client
        self.api_key = openalex_api_key
        self.executions: list[dict[str, object]] = []

    async def search(self, provider: str, query: str) -> tuple[DiscoveryLead, ...]:
        started = time.monotonic()
        metric: dict[str, object] = {
            "provider": provider,
            "query": query,
            "status": "failed",
            "cache_hit": False,
            "http_requests": 0,
            "latency_ms": 0,
            "returned": 0,
            "model_calls": 0,
        }
        try:
            if provider == "europe_pmc":
                url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
                params = {"query": query, "format": "json", "resultType": "lite", "pageSize": "10"}
            elif provider == "openalex":
                url = "https://api.openalex.org/works"
                params = {
                    "search": query,
                    "per-page": "10",
                    "select": "id,ids,doi,title,type,is_retracted,publication_year",
                }
            else:
                raise ValueError("Unknown discovery provider")
            key = (
                "discovery:v2:"
                + hashlib.sha256(
                    json.dumps([provider, params], sort_keys=True).encode()
                ).hexdigest()
            )
            cached = await self.cache.get(key) if self.cache else None
            if cached is not None:
                try:
                    data = json.loads(cached)
                    leads = self._parse(provider, data)
                    metric["cache_hit"] = True
                except (ValueError, TypeError, KeyError):
                    cached = None
            if cached is None:
                if provider == "openalex" and self.api_key:
                    params["api_key"] = self.api_key
                async with asyncio.timeout(9):
                    metric["http_requests"] = 1
                    if provider == "europe_pmc":
                        record_source_http("europe_pmc", "search")
                    else:
                        record_source_http("openalex", "search")
                    if self.client:
                        response = await self.client.get(url, params=params, timeout=8)
                    else:
                        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                            response = await client.get(url, params=params)
                    metric["http_status"] = response.status_code
                    response.raise_for_status()
                    if len(response.content) > 1_000_000:
                        raise ValueError("Discovery response exceeds bound")
                    data = response.json()
                    leads = self._parse(provider, data)
                if self.cache:
                    await self.cache.set(key, json.dumps(data), 21600)
            metric.update(status="ok", returned=len(leads))
            return tuple(replace(lead, query=query) for lead in leads)
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
            # No exception URL/query params are logged: an API key may be present.
            metric["failure"] = (
                "deadline" if time.monotonic() - started >= 8 else "provider_response"
            )
            return ()
        finally:
            metric["latency_ms"] = round((time.monotonic() - started) * 1000)
            metric["started_monotonic_ms"] = round(started * 1000)
            metric["finished_monotonic_ms"] = round(time.monotonic() * 1000)
            self.executions.append(metric)

    @staticmethod
    def _parse(provider: str, data: dict[str, Any]) -> tuple[DiscoveryLead, ...]:
        rows = data["resultList"]["result"] if provider == "europe_pmc" else data["results"]
        if not isinstance(rows, list):
            raise ValueError("Invalid discovery envelope")
        leads = []
        for item in rows[:10]:
            if not isinstance(item, dict) or not isinstance(item.get("title"), str):
                continue
            if provider == "europe_pmc":
                pmid = str(
                    item.get("pmid") or (item.get("id") if item.get("source") == "MED" else "")
                )
                doi = item.get("doi")
                identifier = f"{item.get('source')}:{item.get('id')}"
                kind = str(item.get("pubType") or item.get("pubTypeList") or "unverified")
            else:
                ids = item.get("ids") or {}
                pmid = str(ids.get("pmid") or "").rstrip("/").split("/")[-1]
                doi = item.get("doi")
                identifier = str(item.get("id") or "")
                kind = str(item.get("type") or "unverified")
            if item.get("is_retracted") is True:
                kind = "retracted"
            doi = re.sub(r"^https?://(?:dx\.)?doi.org/", "", str(doi), flags=re.I) if doi else None
            leads.append(
                DiscoveryLead(
                    provider, identifier, pmid if pmid.isdigit() else None, doi, item["title"], kind
                )
            )
        return tuple(leads)
