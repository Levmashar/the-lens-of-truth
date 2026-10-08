"""Group approved sources are fetched once, while excerpts cover every assertion."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from app.adapters.authoritative import (
    ApprovedSource,
    AuthoritativeAdapter,
    SourceManifest,
    freeze_html,
)
from app.adapters.source_metrics import source_http_metrics
from app.pipeline.pico import NormalizedPico
from app.retrieval.models import ClaimSnapshot

NOW = datetime.now(UTC)
HTML = (
    '<main id="evidence"><h2>Smoking</h2>'
    + "".join(
        f"<p>Smoking causes lung cancer, with source detail {i} retained exactly.</p>"
        for i in range(8)
    )
    + "<h2>Sunscreen</h2>"
    + "".join(
        f"<p>Sunscreen reduces melanoma risk, with endpoint detail {i} retained exactly.</p>"
        for i in range(8)
    )
    + f'</main><time datetime="{NOW.date().isoformat()}">Updated</time>'
)


def _source():
    return ApprovedSource(
        source_id="fixture-nci",
        organization="NCI",
        canonical_url="https://www.cancer.gov/fixture",
        document_title="Synthetic approved source",
        document_purpose="causal_assessment",
        topic_terms=("smoking", "sunscreen"),
        root_attribute="id",
        root_value="evidence",
        last_verified_at=NOW,
        retrieval_method="html_blocks",
        independence_group="fixture-body",
        attribution="Synthetic fixture, not an actual NCI document.",
    )


def _claim(text, exposure, outcome):
    return ClaimSnapshot(
        claim_id=uuid4(),
        raw_text=text,
        claim_type="causal",
        pico=NormalizedPico(
            original_claim=text,
            intervention_or_exposure=exposure,
            outcome=outcome,
            claim_type="causal",
        ),
    )


def _claims():
    return (
        _claim("Smoking causes lung cancer.", "Smoking", "lung cancer"),
        _claim("Daily sunscreen use reduces melanoma risk.", "sunscreen", "melanoma"),
    )


def test_group_fetches_once_and_second_assertion_keeps_its_distinct_source_blocks():
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})

    async def run():
        cache = {}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = AuthoritativeAdapter(
                SourceManifest(version="fixture", sources=(_source(),)), client=client
            )
            with source_http_metrics() as first_counts:
                first, statuses = await adapter.retrieve_group(_claims(), document_cache=cache)
            with source_http_metrics() as next_counts:
                later, _ = await adapter.retrieve_group((_claims()[1],), document_cache=cache)
            return first, later, statuses, cache, first_counts, next_counts

    first, later, statuses, cache, first_counts, next_counts = asyncio.run(run())

    assert requests == ["/fixture"]
    assert first_counts == {"authoritative.document": 1}
    assert next_counts == {}
    assert statuses == {"fixture-nci": "current"}
    assert len(first) == len(later) == 1
    assert len(first[0].abstract_sections) == 16
    assert any("lung cancer" in s.text for s in first[0].abstract_sections)
    assert any("melanoma" in s.text for s in first[0].abstract_sections)
    assert len(cache["authoritative:fixture-nci"].abstract_sections) == 16
    assert len(later[0].abstract_sections) == 8
    assert all("melanoma" in s.text for s in later[0].abstract_sections)
    assert later[0].authoritative.omitted_block_count == 8


@pytest.mark.parametrize("cache_change", ["expired", "clipped", "changed_manifest", "tampered"])
def test_incomplete_outdated_or_wrong_manifest_cache_is_refetched(cache_change):
    source = _source()
    raw = freeze_html(source, HTML, now=NOW)
    if cache_change == "expired":
        raw = raw.model_copy(update={"retrieved_at": NOW - timedelta(hours=7)})
    elif cache_change == "clipped":
        raw = raw.model_copy(
            update={
                "abstract_sections": raw.abstract_sections[:8],
                "authoritative": raw.authoritative.model_copy(
                    update={
                        "retained_block_count": 8,
                        "omitted_block_count": 8,
                    }
                ),
            }
        )
    elif cache_change == "changed_manifest":
        source = source.model_copy(update={"attribution": "New approved manifest attribution"})
    else:
        sections = (
            raw.abstract_sections[0].model_copy(update={"text": "Altered exact source text"}),
            *raw.abstract_sections[1:],
        )
        raw = raw.model_copy(
            update={
                "abstract_sections": sections,
                "abstract": "\n".join(s.text for s in sections),
            }
        )
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = AuthoritativeAdapter(
                SourceManifest(version="fixture", sources=(source,)), client=client
            )
            return await adapter.retrieve_group(_claims(), document_cache={raw.document_id: raw})

    docs, statuses = asyncio.run(run())

    assert attempts == 1
    assert statuses == {"fixture-nci": "current"}
    assert len(docs[0].abstract_sections) == 16


def test_missing_document_update_date_remains_unknown_on_cache_reuse():
    source = _source()
    html = HTML.split('<time datetime="')[0]
    cache = {}

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    text=html,
                    headers={"content-type": "text/html"},
                )
            )
        ) as client:
            adapter = AuthoritativeAdapter(
                SourceManifest(version="fixture", sources=(source,)), client=client
            )
            first, _ = await adapter.retrieve_group(_claims(), document_cache=cache)
            with source_http_metrics() as counts:
                second, statuses = await adapter.retrieve_group(_claims(), document_cache=cache)
        return first, second, statuses, counts

    first, second, statuses, counts = asyncio.run(run())

    assert statuses == {"fixture-nci": "unknown"}
    assert first[0].integrity.status == second[0].integrity.status == "unknown"
    assert counts == {}


def test_unavailable_approved_source_is_attempted_once_for_the_whole_group():
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(503)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = AuthoritativeAdapter(
                SourceManifest(version="fixture", sources=(_source(),)), client=client
            )
            return await adapter.retrieve_group(_claims())

    docs, statuses = asyncio.run(run())

    assert attempts == 1
    assert docs == ()
    assert statuses == {"fixture-nci": "unavailable"}


def test_ordinary_single_claim_excerpt_behavior_is_unchanged():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    text=HTML,
                    headers={"content-type": "text/html"},
                )
            )
        ) as client:
            adapter = AuthoritativeAdapter(
                SourceManifest(version="fixture", sources=(_source(),)), client=client
            )
            return await adapter.retrieve(_claims()[0])

    docs, statuses = asyncio.run(run())

    assert statuses == {"fixture-nci": "current"}
    assert len(docs[0].abstract_sections) == 8
    assert all("lung cancer" in s.text for s in docs[0].abstract_sections)
    assert docs[0].authoritative.omitted_block_count == 8
