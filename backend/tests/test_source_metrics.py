"""Public-source HTTP counts are passive, content-free and isolated by group task."""

import asyncio
import json
from typing import cast

import httpx
import pytest

from app.adapters.authoritative import AuthoritativeAdapter
from app.adapters.crossref import CrossrefAdapter
from app.adapters.pubmed import PubMedAdapter
from app.adapters.source_metrics import (
    SourceOperation,
    SourceProvider,
    record_ncbi_source_http,
    record_source_http,
    source_http_metrics,
)
from app.retrieval.errors import RetrievalError


class MemoryCache:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ttl_seconds):
        self.values[key] = value


def test_default_is_passive_and_nested_scope_restores_even_after_exception():
    record_source_http("pubmed", "search")
    with source_http_metrics() as outer:
        assert outer == {}
        record_source_http("pubmed", "search")
        with pytest.raises(ValueError, match="scope"):
            with source_http_metrics() as inner:
                record_source_http("pmc", "fetch")
                raise ValueError("scope")
        record_source_http("pubmed", "search")
    record_source_http("pubmed", "search")

    assert outer == {"pubmed.search": 2}
    assert inner == {"pmc.fetch": 1}


def test_concurrent_groups_are_isolated_and_joined_child_tasks_share_group_counts():
    async def group(provider):
        with source_http_metrics() as counts:
            async def child():
                await asyncio.sleep(0)
                record_source_http(provider, "fetch")
            await asyncio.gather(child(), child())
            return dict(counts)

    async def run():
        return await asyncio.gather(group("pubmed"), group("pmc"))

    assert asyncio.run(run()) == [{"pubmed.fetch": 2}, {"pmc.fetch": 2}]


def test_only_fixed_operation_keys_can_enter_metrics():
    with source_http_metrics() as counts:
        record_ncbi_source_http("esearch.fcgi", database="pubmed")
        record_ncbi_source_http("elink.fcgi", database="pubmed", source_database="pmc")
        record_ncbi_source_http("elink.fcgi", database="pmc", source_database="pubmed")
        record_ncbi_source_http("efetch.fcgi", database="pmc")
        record_ncbi_source_http("https://private.example/?api_key=example-secret", database="pmc")
        record_ncbi_source_http("esearch.fcgi", database="untrusted-private-value")
        record_source_http(cast(SourceProvider, "private-value"), "search")
        record_source_http("pubmed", cast(SourceOperation, "private-value"))

    assert counts == {"pubmed.search": 1, "pmc.link": 2, "pmc.fetch": 1}
    assert "private" not in json.dumps(counts)
    assert "secret" not in json.dumps(counts)


def test_pubmed_wire_retries_count_and_cache_hit_does_not_count():
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"esearchresult": {"idlist": ["100"], "count": "1"}})

    async def run():
        async with httpx.AsyncClient(
            base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
            transport=httpx.MockTransport(handler),
        ) as client:
            adapter = PubMedAdapter(
                tool="fixture", email="fixture@example.test", api_key="fixture-secret",
                max_retries=1, minimum_interval_seconds=0, cache=MemoryCache(), client=client,
            )
            with source_http_metrics() as first:
                result = await adapter.search("private submitted medical phrase")
            with source_http_metrics() as second:
                cached = await adapter.search("private submitted medical phrase")
        return first, second, result, cached

    first, second, result, cached = asyncio.run(run())

    assert attempts == 2
    assert first == {"pubmed.search": 2}
    assert second == {}
    assert result == (("100",), False)
    assert cached == (("100",), True)
    assert "fixture-secret" not in json.dumps(first)
    assert "medical" not in json.dumps(first)


def test_crossref_wire_retries_count_and_cache_hit_does_not_count():
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"status": "ok", "message": {"DOI": "10.1234/private"}})

    async def run():
        async with httpx.AsyncClient(
            base_url="https://api.crossref.org/v1/", transport=httpx.MockTransport(handler),
        ) as client:
            adapter = CrossrefAdapter(
                mailto="private-contact@example.test", cache=MemoryCache(), client=client,
            )
            with source_http_metrics() as first:
                result = await adapter.enrich("10.1234/private")
            with source_http_metrics() as second:
                cached = await adapter.enrich("10.1234/private")
        return first, second, result, cached

    first, second, result, cached = asyncio.run(run())

    assert attempts == 2
    assert first == {"crossref.work": 2}
    assert second == {}
    assert result == cached
    assert result.check.status == "checked"
    assert "private" not in json.dumps(first)


def test_authoritative_stream_sends_count_once_each_and_expose_no_url():
    def handler(request):
        return httpx.Response(200, text="<main>approved body</main>", headers={
            "content-type": "text/html",
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with source_http_metrics() as counts:
                html = await AuthoritativeAdapter._read(client, "https://example.test/private")
        return counts, html

    counts, html = asyncio.run(run())

    assert counts == {"authoritative.document": 1}
    assert html == "<main>approved body</main>"
    assert "example" not in json.dumps(counts)


def test_transport_failure_still_counts_the_initiated_wire_attempt():
    def handler(request):
        raise httpx.ConnectError("fixture", request=request)

    async def run():
        async with httpx.AsyncClient(
            base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
            transport=httpx.MockTransport(handler),
        ) as client:
            adapter = PubMedAdapter(
                tool="fixture", email="fixture@example.test", max_retries=0,
                minimum_interval_seconds=0, client=client,
            )
            with source_http_metrics() as counts:
                with pytest.raises(RetrievalError):
                    await adapter.search("fixture")
        return counts

    assert asyncio.run(run()) == {"pubmed.search": 1}
