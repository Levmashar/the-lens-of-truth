"""Controlled discovery of official guidance, always background-only.

Search titles/snippets never become evidence. Fetch exact allowlisted HTTPS
origins, visible main/article content, title and canonical metadata; freeze it.
Automated origin verification is not editorial/clinical currency approval.
"""

import asyncio
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

import httpx

from app.adapters.authoritative import ApprovedSource, freeze_html
from app.adapters.pubmed import QueryCache
from app.adapters.source_metrics import record_source_http
from app.retrieval.adaptive import concepts
from app.retrieval.models import ClaimSnapshot, DocumentIntegrity, PubMedDocument

HOSTS = {
    "www.nhs.uk": "NHS",
    "www.nei.nih.gov": "NIH/NEI",
    "medlineplus.gov": "NIH/MedlinePlus",
    "www.cdc.gov": "CDC",
    "www.cancer.gov": "NCI",
    "www.who.int": "WHO",
    "www.aao.org": "AAO",
    "www.aap.org": "AAP",
    "www.nccih.nih.gov": "NIH/NCCIH",
}


def safe_url(value: str) -> str | None:
    try:
        u = urlsplit(value)
        if (
            u.scheme != "https"
            or u.hostname not in HOSTS
            or u.username
            or u.password
            or u.port is not None
            or u.query
            or "\\" in value
        ):
            return None
        if (
            not u.path
            or u.path == "/"
            or re.search(r"/(?:search|news|press|login|about)(?:/|$)", u.path)
        ):
            return None
        return urlunsplit(("https", u.hostname, u.path, "", ""))
    except ValueError:
        return None


class PageMetadata(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.canonical: str | None = None
        self.title = ""
        self.in_title = False
        self.in_main = False
        self.in_nav = False
        self.stack: list[str] = []
        self.root_depth: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag not in {"br", "hr", "img", "meta", "link", "input", "wbr", "source"}:
            self.stack.append(tag)
        if tag == "main" or a.get("role") == "main" or a.get("id") == "mplus-content":
            self.in_main = True
            self.root_depth = len(self.stack)
        if tag == "nav":
            self.in_nav = True
        if tag == "a" and a.get("href") and self.in_main and not self.in_nav:
            self.links.append(a["href"] or "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        if tag == "h1":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index] == tag:
                del self.stack[index:]
                break
        if self.root_depth is not None and self.root_depth > len(self.stack):
            self.in_main = False
            self.root_depth = None
        if tag == "nav":
            self.in_nav = False
        if tag == "h1":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data


class OfficialWebDiscovery:
    def __init__(
        self, *, cache: QueryCache | None = None, client: httpx.AsyncClient | None = None
    ) -> None:
        self.cache, self.client = cache, client
        self.executions: list[dict[str, object]] = []

    async def _get(self, url: str, params: dict[str, str] | None = None) -> str:
        async def read(client: httpx.AsyncClient) -> str:
            async with client.stream(
                "GET", url, params=params, timeout=6, follow_redirects=False
            ) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError("Redirects not accepted")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise ValueError("Official page exceeds bound")
                return bytes(body).decode(response.encoding or "utf-8", errors="replace")

        async with asyncio.timeout(6):
            if self.client:
                return await read(self.client)
            async with httpx.AsyncClient(timeout=6, trust_env=False, follow_redirects=False) as c:
                return await read(c)

    async def retrieve(self, claim: ClaimSnapshot, query: str) -> tuple[PubMedDocument, ...]:
        async def search(provider: str) -> list[str]:
            started = time.monotonic()
            metric: dict[str, object] = {
                "provider": provider,
                "operation": "search",
                "http_requests": 0,
                "cache_hit": False,
                "status": "failed",
            }
            search_query = " ".join(concepts(claim, "outcome", core=True)[:1])
            key = (
                "official-search:v2.3:"
                + hashlib.sha256((provider + search_query).encode()).hexdigest()
            )
            try:
                cached = await self.cache.get(key) if self.cache else None
                if cached:
                    links = json.loads(cached)
                    metric["cache_hit"] = True
                else:
                    metric["http_requests"] = 1
                    record_source_http("official_web", "search")
                    if provider == "nhs_search":
                        url = "https://www.nhs.uk/search/results"
                        html = await self._get(url, {"q": search_query})
                        parser = PageMetadata()
                        parser.feed(html)
                        links = []
                        for link in parser.links:
                            parsed = urlsplit(urljoin(url, link))
                            if parsed.path == "/search/click":
                                target = parse_qs(parsed.query).get("url", [""])[0]
                                if target.startswith("/") and not target.startswith("//"):
                                    links.append(urljoin(url, target))
                            else:
                                links.append(urljoin(url, link))
                    else:
                        xml = await self._get(
                            "https://wsearch.nlm.nih.gov/ws/query",
                            {"db": "healthTopics", "term": search_query, "retmax": "3"},
                        )
                        links = [n.get("url") for n in ET.fromstring(xml).findall(".//document")]
                    links = list(
                        dict.fromkeys(u for link in links if link and (u := safe_url(link)))
                    )[:6]
                    if self.cache:
                        await self.cache.set(key, json.dumps(links), 21600)
                metric.update(status="ok", returned=len(links))
                return [u for link in links if (u := safe_url(link))]
            except (httpx.HTTPError, TimeoutError, ValueError, ET.ParseError, TypeError):
                return []
            finally:
                metric["latency_ms"] = round((time.monotonic() - started) * 1000)
                metric["started_monotonic_ms"] = round(started * 1000)
                metric["finished_monotonic_ms"] = round(time.monotonic() * 1000)
                self.executions.append(metric)

        # Two documented/native official indexes; no general-search snippets.
        batches = await asyncio.gather(search("nhs_search"), search("medlineplus_search"))
        # Reserve one lead per index instead of letting one index consume all slots.
        urls = list(dict.fromkeys(batch[0] for batch in batches if batch))[:2]

        async def fetch(url: str, parent: str | None = None) -> PubMedDocument | None:
            started = time.monotonic()
            metric: dict[str, object] = {
                "provider": "official_web",
                "operation": "document",
                "url": url,
                "http_requests": 0,
                "cache_hit": False,
                "status": "rejected",
            }
            key = "official-page:v2:" + hashlib.sha256(url.encode()).hexdigest()
            try:
                html = await self.cache.get(key) if self.cache else None
                if html:
                    metric["cache_hit"] = True
                else:
                    metric["http_requests"] = 1
                    record_source_http("official_web", "document")
                    html = await self._get(url)
                parser = PageMetadata()
                parser.feed(html)
                if not parser.title.strip() or not parser.canonical:
                    raise ValueError("Missing page title/canonical identity")
                if safe_url(urljoin(url, parser.canonical)) != url:
                    raise ValueError("Canonical identity mismatch")
                source = ApprovedSource(
                    source_id="discovered-" + hashlib.sha256(url.encode()).hexdigest()[:16],
                    organization=HOSTS[urlsplit(url).hostname or ""],
                    canonical_url=url,
                    document_title=" ".join(parser.title.split()),
                    document_purpose="patient_information",
                    topic_terms=(query,),
                    root_attribute="id" if urlsplit(url).hostname == "medlineplus.gov" else "tag",
                    root_value="topic" if urlsplit(url).hostname == "medlineplus.gov" else "main",
                    last_verified_at=datetime.now(UTC),
                    retrieval_method="html_lists",
                    independence_group=urlsplit(url).hostname or "",
                    attribution="Official origin; background guidance",
                )
                doc = freeze_html(source, html, now=datetime.now(UTC))
                # No claims that a newly discovered page passed manual approval.
                assert doc.authoritative is not None
                doc = doc.model_copy(
                    update={
                        "authoritative": doc.authoritative.model_copy(
                            update={
                                "currency": "unknown",
                                "extraction_version": "official-main-2.0",
                                "reference_urls": tuple(
                                    sorted(
                                        set(doc.authoritative.reference_urls)
                                        | {
                                            u
                                            for link in parser.links
                                            if (u := safe_url(urljoin(url, link)))
                                        }
                                    )
                                ),
                            }
                        ),
                        "integrity": DocumentIntegrity(
                            status="unknown",
                            sources=(source.organization,),
                            check_version="official-origin-2.0",
                            warnings=("origin_verified_not_clinical_currency_reviewed",),
                        ),
                        "metadata_provenance": {
                            **doc.metadata_provenance,
                            "purpose": "background_only_automated_origin_verification",
                            "discovered_by:official_web": url,
                            **({"discovered_by:official_link": parent} if parent else {}),
                        },
                        "evidence_role_hint": "contextual",
                    }
                )
                if len(doc.abstract or "") < 150:
                    raise ValueError("No substantive official content")
                if self.cache and not metric["cache_hit"]:
                    await self.cache.set(key, html, 21600)
                metric.update(status="ok", title=doc.title, content_sha256=doc.content_sha256)
                return doc
            except (httpx.HTTPError, TimeoutError, ValueError, KeyError) as exc:
                metric["rejection_reason"] = (
                    str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                )
                if isinstance(exc, httpx.HTTPStatusError):
                    metric["http_status"] = exc.response.status_code
                return None
            finally:
                metric["latency_ms"] = round((time.monotonic() - started) * 1000)
                metric["started_monotonic_ms"] = round(started * 1000)
                metric["finished_monotonic_ms"] = round(time.monotonic() * 1000)
                self.executions.append(metric)

        docs = await asyncio.gather(*(fetch(u) for u in urls))
        result = tuple(d for d in docs if d)
        # One hop, one page, and only a reference published inside verified content.
        # This permits society/NIH discovery without trusting a general web result.
        references = [
            (d.canonical_url, u)
            for d in result
            if d.authoritative
            for link in d.authoritative.reference_urls
            if (u := safe_url(link))
            and u not in urls
            and urlsplit(u).hostname not in {"www.nhs.uk", "medlineplus.gov"}
        ]
        references.sort(
            key=lambda pair: (
                urlsplit(pair[1]).hostname not in {"www.aao.org", "www.aap.org"},
                pair[1],
            )
        )
        if references:
            parent, url = references[0]
            extra = await fetch(url, parent)
            if extra:
                result = (*result, extra)
        return result
