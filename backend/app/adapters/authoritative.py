"""Bounded fetch of reviewed canonical documents. No search, crawler or user URL."""

import asyncio
import hashlib
import json
import re
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import Field, model_validator

from app.adapters.source_metrics import record_source_http
from app.retrieval.directness import _matches
from app.retrieval.models import (
    AbstractSection,
    AuthoritativeMetadata,
    ClaimSnapshot,
    DocumentIntegrity,
    DocumentPurpose,
    FrozenModel,
    PubMedDocument,
)
from app.retrieval.ranking import _aliases, _words

MANIFEST_PATH = Path(__file__).parents[1] / "retrieval" / "authoritative_manifest.json"
_ORGANIZATIONS = {
    "NCI": "www.cancer.gov",
    "CDC": "www.cdc.gov",
    "WHO": "www.who.int",
    "IARC": "www.iarc.who.int",
    "NIH/NCCIH": "www.nccih.nih.gov",
}
_ADDITIONAL_APPROVED_HOSTS = {"CDC": {"hivrisk.cdc.gov"}}


class ApprovedSource(FrozenModel):
    source_id: str = Field(pattern=r"^[a-z0-9-]{1,64}$")
    organization: str
    canonical_url: str
    document_title: str
    document_purpose: DocumentPurpose
    topic_terms: tuple[str, ...]
    root_attribute: Literal["id", "class", "tag"]
    root_value: str
    last_verified_at: datetime
    retrieval_method: Literal["html_blocks", "html_lists"]
    independence_group: str
    attribution: str

    @model_validator(mode="after")
    def approved_domain(self) -> "ApprovedSource":
        url = urlsplit(self.canonical_url)
        hosts = {_ORGANIZATIONS.get(self.organization)} | _ADDITIONAL_APPROVED_HOSTS.get(
            self.organization, set()
        )
        if (
            url.scheme != "https"
            or url.hostname not in hosts
            or url.username
            or url.password
            or url.port
            or url.query
            or url.fragment
        ):
            raise ValueError("Manifest URL is not a canonical approved organization URL")
        return self


class SourceManifest(FrozenModel):
    version: str
    sources: tuple[ApprovedSource, ...]

    @model_validator(mode="after")
    def unique_sources(self) -> "SourceManifest":
        if len({s.source_id for s in self.sources}) != len(self.sources) or len(
            {s.canonical_url for s in self.sources}
        ) != len(self.sources):
            raise ValueError("Duplicate manifest source")
        return self


def load_manifest(path: Path = MANIFEST_PATH) -> SourceManifest:
    return SourceManifest.model_validate_json(path.read_text(encoding="utf-8"))


class HtmlBlocks(HTMLParser):
    """Exact visible block text after documented entity/HTML whitespace normalization.

    No JS, hidden reasoning or header/footer/nav extraction. Offsets refer to
    these canonical frozen blocks, NOT byte positions in the HTML resource.
    """

    def __init__(self, source: ApprovedSource) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.stack: list[tuple[str, bool, bool]] = []
        self.blocks: list[AbstractSection] = []
        self.buffer: list[str] = []
        self.block_tag: str | None = None
        self.heading = "DOCUMENT"
        self.references: set[str] = set()
        self.list_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        match = (
            tag == self.source.root_value
            if self.source.root_attribute == "tag"
            else self.source.root_value in (values.get(self.source.root_attribute) or "").split()
        )
        inside = match or bool(self.stack and self.stack[-1][1])
        skip = (
            bool(self.stack and self.stack[-1][2])
            or tag
            in {
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "noscript",
                "table",
            }
            or "hidden" in values
            or values.get("aria-hidden") == "true"
        )
        if tag not in {"br", "hr", "img", "input", "meta", "link", "wbr"}:
            self.stack.append((tag, inside, skip))
        if not inside or skip:
            return
        if self.source.retrieval_method == "html_lists" and tag in {"ul", "ol"}:
            if not self.list_depth:
                self.flush()
                # Preserve a list's preceding relation/negation as part of the
                # same exact visible-text block, never an isolated route name.
                if self.blocks and re.search(
                    r"(?:[:]|\bby|\bthrough)\s*$", self.blocks[-1].text, re.I
                ):
                    self.buffer.append(self.blocks.pop().text + " ")
                self.block_tag = tag
            self.list_depth += 1
            return
        if self.list_depth:
            if tag == "li":
                self.buffer.append(" ")
            return
        if tag == "a" and values.get("href"):
            link = urljoin(self.source.canonical_url, values["href"] or "")
            if urlsplit(link).scheme == "https":
                self.references.add(link)
        if match and tag == "div":
            self.block_tag = tag  # Some official abstracts are unwrapped root text.
        if tag in {"p", "li", "h1", "h2", "h3", "h4"}:
            self.flush()
            self.block_tag = tag
        if tag == "br" and self.block_tag:
            self.buffer.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self.list_depth and tag in {"ul", "ol"}:
            self.list_depth -= 1
        if tag == self.block_tag and not self.list_depth:
            self.flush()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.block_tag and self.stack and self.stack[-1][1] and not self.stack[-1][2]:
            self.buffer.append(data)

    def flush(self) -> None:
        text = " ".join("".join(self.buffer).split())
        if text and self.block_tag:
            if self.block_tag.startswith("h"):
                self.heading = text
            elif 20 <= len(text) <= 4800:
                self.blocks.append(AbstractSection(label=self.heading, text=text))
        self.buffer = []
        self.block_tag = None


def update_date(html: str) -> date | None:
    # Only explicitly marked document dates; never the HTTP Date or fetch date.
    # Site-wide footer dates are not the document's update date.
    html = re.sub(r"<!--[\s\S]*?-->", "", html)
    html = re.sub(r"<footer\b(?![^>]*article-footer)[\s\S]*?</footer>", "", html, flags=re.I)
    html = re.sub(r"Site Last Updated:[\s\S]{0,100}", "", html, flags=re.I)
    patterns = (
        r'<time[^>]*datetime=["\'](\d{4}-\d{2}-\d{2})',
        r'"dateModified"\s*:\s*"(\d{4}-\d{2}-\d{2})',
        r"(?:Updated|Reviewed|Last updated)\s*:?[\s<][\s\S]{0,90}?(\w+ \d{1,2}, \d{4})",
        r'<div class="date">\s*(\d{1,2} \w+ \d{4})',
    )
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if not match:
            continue
        for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y"):
            try:
                return datetime.strptime(match.group(1), fmt).date()
            except ValueError:
                pass
    return None


def source_relevant(claim: ClaimSnapshot, source: ApprovedSource) -> bool:
    text = " ".join((claim.standalone_text, *(e.preferred_name or "" for e in claim.entities)))
    return any(_words(term) <= _words(text) for term in source.topic_terms if _words(term))


def freeze_html(
    source: ApprovedSource,
    html: str,
    *,
    now: datetime,
    max_age_days: int = 3650,
    verified_age_days: int = 90,
) -> PubMedDocument:
    parser = HtmlBlocks(source)
    parser.feed(html)
    parser.flush()
    if not parser.blocks:
        raise ValueError("Approved content root has no evidence blocks")
    updated = update_date(html)
    currency: Literal["current", "stale", "unknown"] = "unknown"
    if updated and updated <= now.date():
        currency = "stale" if (now.date() - updated).days > max_age_days else "current"
    if (now - source.last_verified_at).days > verified_age_days:
        currency = "stale"
    blocks = tuple(parser.blocks)
    digest = hashlib.sha256(
        json.dumps(
            {
                "source_id": source.source_id,
                "url": source.canonical_url,
                "title": source.document_title,
                "purpose": source.document_purpose,
                "updated": str(updated),
                "sections": [s.model_dump() for s in blocks],
                "references": sorted(parser.references),
                "extraction_version": (
                    "approved-html-1.1"
                    if source.retrieval_method == "html_lists"
                    else "approved-html-1.0"
                ),
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    pmids = tuple(
        sorted(
            {
                m.group(1)
                for url in parser.references
                if (
                    m := re.search(
                        r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|"
                        r"www\.ncbi\.nlm\.nih\.gov/pubmed/)(\d+)",
                        url,
                    )
                )
            }
        )
    )
    meta = AuthoritativeMetadata(
        source_id=source.source_id,
        organization=source.organization,
        document_purpose=source.document_purpose,
        last_verified_at=source.last_verified_at,
        updated_at=updated,
        content_version=digest,
        currency=currency,
        reference_urls=tuple(sorted(parser.references)),
        underlying_pmids=pmids,
        underlying_studies_known=bool(pmids),
        independence_group=source.independence_group,
        attribution=source.attribution,
        retained_block_count=len(blocks),
        extraction_version="approved-html-1.1"
        if source.retrieval_method == "html_lists"
        else "approved-html-1.0",
    )
    return PubMedDocument(
        document_id=f"authoritative:{source.source_id}",
        pmid="",
        title=source.document_title,
        abstract="\n".join(s.text for s in blocks),
        abstract_sections=blocks,
        canonical_url=source.canonical_url,
        publication_date=updated,
        retrieved_at=now,
        content_sha256=digest,
        source_kind="authoritative_public_health",
        authoritative=meta,
        integrity=DocumentIntegrity(
            status="valid" if currency == "current" else "unknown",
            sources=(source.organization,),
            check_version="approved-source-1.0",
            warnings=() if currency == "current" else (f"source_currency_{currency}",),
        ),
        metadata_provenance={
            "content": source.canonical_url,
            "purpose": "reviewed_manifest",
            "update_date": "document" if updated else "absent",
        },
    )


class AuthoritativeAdapter:
    def __init__(
        self,
        manifest: SourceManifest,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 12,
        max_age_days: int = 3650,
        verified_age_days: int = 90,
    ) -> None:
        self.manifest = manifest
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.max_age_days = max_age_days
        self.verified_age_days = verified_age_days

    async def fetch(self, source_id: str) -> PubMedDocument:
        source = next((s for s in self.manifest.sources if s.source_id == source_id), None)
        if source is None:
            raise ValueError("Source ID is outside approved manifest")
        async with asyncio.timeout(self.timeout_seconds):
            if self.client:
                html = await self._read(self.client, source.canonical_url)
            else:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds, follow_redirects=False, trust_env=False
                ) as client:
                    html = await self._read(client, source.canonical_url)
        return freeze_html(
            source,
            html,
            now=datetime.now(UTC),
            max_age_days=self.max_age_days,
            verified_age_days=self.verified_age_days,
        )

    @staticmethod
    async def _read(client: httpx.AsyncClient, url: str) -> str:
        record_source_http("authoritative", "document")
        async with client.stream("GET", url, follow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError("Approved source unavailable; redirects are not followed")
            if "html" not in response.headers.get("content-type", ""):
                raise ValueError("Unsupported approved source response")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > 2_000_000:
                    raise ValueError("Approved response size limit exceeded")
                body.extend(chunk)
            return bytes(body).decode(response.encoding or "utf-8", errors="replace")

    async def retrieve(
        self, claim: ClaimSnapshot
    ) -> tuple[tuple[PubMedDocument, ...], dict[str, str]]:
        selected = [s for s in self.manifest.sources if source_relevant(claim, s)][:4]
        semaphore = asyncio.Semaphore(2)
        statuses: dict[str, str] = {}

        async def one(source: ApprovedSource) -> PubMedDocument | None:
            async with semaphore:
                try:
                    doc = await self.fetch(source.source_id)
                    statuses[source.source_id] = (
                        doc.authoritative.currency if doc.authoritative else "unknown"
                    )
                    # Bound retained excerpts to the question, preserving complete
                    # paragraphs (and negations), not a hand-picked support direction.
                    terms = _words(claim.standalone_text)
                    terms |= _words(" ".join(_aliases(claim, "outcome")))
                    indexed = sorted(
                        enumerate(doc.abstract_sections),
                        key=lambda pair: (
                            -int(
                                _matches(
                                    (pair[1].label or "") + " " + pair[1].text,
                                    _aliases(claim, "intervention_or_exposure"),
                                    concept_flex=True,
                                )
                            ),
                            -len(terms & _words(pair[1].text)),
                            pair[0],
                        ),
                    )
                    chosen: set[int] = set()
                    retained_chars = 0
                    for i, section in indexed:
                        if len(chosen) >= 8:
                            break
                        if retained_chars + len(section.text) <= 8000:
                            chosen.add(i)
                            retained_chars += len(section.text)
                    sections = tuple(s for i, s in enumerate(doc.abstract_sections) if i in chosen)
                    assert doc.authoritative is not None
                    metadata = doc.authoritative.model_copy(
                        update={
                            "retained_block_count": len(sections),
                            "omitted_block_count": len(doc.abstract_sections) - len(sections),
                        }
                    )
                    return doc.model_copy(
                        update={
                            "abstract_sections": sections,
                            "authoritative": metadata,
                            "abstract": "\n".join(s.text for s in sections),
                        }
                    )
                except (httpx.HTTPError, TimeoutError, ValueError):
                    statuses[source.source_id] = "unavailable"
                    return None

        docs = await asyncio.gather(*(one(s) for s in selected))
        return tuple(d for d in docs if d), statuses

    async def retrieve_group(
        self,
        claims: tuple[ClaimSnapshot, ...],
        *,
        document_cache: dict[str, PubMedDocument] | None = None,
        cache_ttl_seconds: int = 21_600,
    ) -> tuple[tuple[PubMedDocument, ...], dict[str, str]]:
        """Fetch each approved source once and retain balanced assertion coverage.

        This document-only path caches complete canonical blocks. Question-specific
        excerpt projections are rebuilt from those blocks for every group.
        The ordinary single-claim adapter keeps its existing behavior.
        """
        if not 1 <= len(claims) <= 8 or not 0 < cache_ttl_seconds <= 21_600:
            raise ValueError("Approved document retrieval exceeds its bounded group scope")
        cache = document_cache if document_cache is not None else {}
        sources: dict[str, ApprovedSource] = {}
        source_claims: dict[str, list[ClaimSnapshot]] = {}
        for claim in claims:
            for source in [s for s in self.manifest.sources if source_relevant(claim, s)][:4]:
                sources.setdefault(source.source_id, source)
                source_claims.setdefault(source.source_id, []).append(claim)
        semaphore = asyncio.Semaphore(2)
        statuses: dict[str, str] = {}

        async def one(source: ApprovedSource) -> PubMedDocument | None:
            async with semaphore:
                try:
                    cache_key = f"authoritative:{source.source_id}"
                    doc = cache.get(cache_key)
                    if doc is None or not self._group_cache_usable(
                        source,
                        doc,
                        datetime.now(UTC),
                        cache_ttl_seconds,
                    ):
                        doc = await self.fetch(source.source_id)
                        cache[cache_key] = doc
                    statuses[source.source_id] = (
                        doc.authoritative.currency if doc.authoritative else "unknown"
                    )
                    return _group_excerpt(doc, tuple(source_claims[source.source_id]))
                except (httpx.HTTPError, TimeoutError, ValueError):
                    statuses[source.source_id] = "unavailable"
                    return None

        docs = await asyncio.gather(*(one(s) for s in sources.values()))
        return tuple(d for d in docs if d), statuses

    def _group_cache_usable(
        self,
        source: ApprovedSource,
        doc: PubMedDocument,
        now: datetime,
        ttl_seconds: int,
    ) -> bool:
        """Reuse only fresh, complete blocks from the exact approved manifest source."""
        meta = doc.authoritative
        if (
            meta is None
            or doc.document_id != f"authoritative:{source.source_id}"
            or doc.canonical_url != source.canonical_url
            or doc.title != source.document_title
            or meta.source_id != source.source_id
            or meta.organization != source.organization
            or meta.document_purpose != source.document_purpose
            or meta.last_verified_at != source.last_verified_at
            or meta.independence_group != source.independence_group
            or meta.attribution != source.attribution
            or meta.omitted_block_count
            or meta.retained_block_count != len(doc.abstract_sections)
            or doc.abstract != "\n".join(s.text for s in doc.abstract_sections)
            or meta.content_version != doc.content_sha256
        ):
            return False
        try:
            age = (now - doc.retrieved_at).total_seconds()
        except TypeError:
            return False
        if not 0 <= age <= ttl_seconds:
            return False
        currency = "unknown"
        if meta.updated_at and meta.updated_at <= now.date():
            currency = (
                "stale" if (now.date() - meta.updated_at).days > self.max_age_days else "current"
            )
        if (now - source.last_verified_at).days > self.verified_age_days:
            currency = "stale"
        extraction_version = (
            "approved-html-1.1" if source.retrieval_method == "html_lists" else "approved-html-1.0"
        )
        digest = hashlib.sha256(
            json.dumps(
                {
                    "source_id": source.source_id,
                    "url": source.canonical_url,
                    "title": source.document_title,
                    "purpose": source.document_purpose,
                    "updated": str(meta.updated_at),
                    "sections": [s.model_dump() for s in doc.abstract_sections],
                    "references": sorted(meta.reference_urls),
                    "extraction_version": extraction_version,
                },
                sort_keys=True,
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        return (
            meta.currency == currency
            and meta.extraction_version == extraction_version
            and digest == doc.content_sha256
        )


def _group_excerpt(doc: PubMedDocument, claims: tuple[ClaimSnapshot, ...]) -> PubMedDocument:
    """Round-robin complete paragraphs; never reuse the first assertion's clipped view."""
    orders = []
    for claim in claims:
        terms = _words(claim.standalone_text) | _words(" ".join(_aliases(claim, "outcome")))
        orders.append(
            sorted(
                range(len(doc.abstract_sections)),
                key=lambda i: (
                    -int(
                        _matches(
                            (doc.abstract_sections[i].label or "")
                            + " "
                            + doc.abstract_sections[i].text,
                            _aliases(claim, "intervention_or_exposure"),
                            concept_flex=True,
                        )
                    ),
                    -len(terms & _words(doc.abstract_sections[i].text)),
                    i,
                ),
            )
        )
    chosen: set[int] = set()
    retained_chars = 0
    max_blocks = min(24, 8 * len(claims))
    max_characters = min(24_000, 8000 * len(claims))
    # Every assertion gets a turn before any receives its second paragraph.
    # The group union is bounded, but source blocks are always kept whole.
    for rank in range(len(doc.abstract_sections)):
        for order in orders:
            index = order[rank]
            if index in chosen:
                continue
            section = doc.abstract_sections[index]
            if len(chosen) < max_blocks and retained_chars + len(section.text) <= max_characters:
                chosen.add(index)
                retained_chars += len(section.text)
        if len(chosen) >= max_blocks:
            break
    sections = tuple(s for i, s in enumerate(doc.abstract_sections) if i in chosen)
    if doc.authoritative is None:
        raise ValueError("Group approved source lacks canonical source metadata")
    metadata = doc.authoritative.model_copy(
        update={
            "retained_block_count": len(sections),
            "omitted_block_count": len(doc.abstract_sections) - len(sections),
        }
    )
    return doc.model_copy(
        update={
            "abstract_sections": sections,
            "authoritative": metadata,
            "abstract": "\n".join(s.text for s in sections),
        }
    )
