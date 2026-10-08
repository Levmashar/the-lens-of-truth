"""Bounded official PMC XML retrieval sharing the existing NCBI request limiter."""

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.adapters.pubmed import PubMedAdapter, QueryCache
from app.retrieval.errors import RetrievalError
from app.retrieval.models import EvidencePassage, PubMedDocument

VERSION: Literal["pmc-jats-1.0"] = "pmc-jats-1.0"


class PmcFullText(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: Literal["pmc-jats-1.0"] = VERSION
    document_id: str
    pmid: str
    pmcid: str | None = None
    status: Literal["available", "not_in_pmc", "metadata_only", "unavailable", "identity_mismatch"]
    content_sha256: str | None = None
    retrieved_at: datetime
    passages: tuple[EvidencePassage, ...] = ()
    locations: dict[str, str] = {}
    limitations: tuple[str, ...] = ()
    omitted_blocks: int = 0
    cache_hit: bool = False
    source_requests: int = 0


def _text(element: ET.Element | None) -> str:
    return "".join(element.itertext()).strip() if element is not None else ""


def _table_text(table: ET.Element) -> str:
    """Project the complete labelled table, retaining headers and footnotes.

    Tabs/newlines mark XML cells/rows. This is a structural source projection,
    not a paraphrase or derived estimate; its exact bytes are hashed and frozen.
    """
    parts = [_text(table.find("label")), _text(table.find("caption"))]
    for row in table.findall(".//table/thead/tr") + table.findall(".//table/tbody/tr"):
        cells = [_text(cell) for cell in row if cell.tag in {"th", "td"}]
        if cells:
            parts.append("\t".join(cells))
    # Some JATS tables have direct rows rather than a tbody.
    for row in table.findall(".//table/tr"):
        parts.append("\t".join(_text(cell) for cell in row if cell.tag in {"th", "td"}))
    parts.append(_text(table.find("table-wrap-foot")))
    return "\n".join(part for part in parts if part)


def parse_pmc_xml(
    xml: bytes, document: PubMedDocument, pmcid: str, *,
    retrieved_at: datetime | None = None,
) -> PmcFullText:
    """Read only owned methods/results/body paragraphs and complete tables."""
    now = retrieved_at or datetime.now(UTC)
    if len(xml) > 4_000_000 or b"<!ENTITY" in xml.upper():
        raise RetrievalError("malformed_response")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise RetrievalError("malformed_response") from exc
    article = root if root.tag == "article" else root.find("article")
    if article is None:
        raise RetrievalError("malformed_response")
    identifiers = {node.get("pub-id-type"): _text(node)
                   for node in article.findall("front/article-meta/article-id")}
    observed_pmid = identifiers.get("pmid")
    observed_pmc = next((identifiers[key] for key in ("pmc", "pmcaid", "pmcid")
                         if key in identifiers), None)
    expected_number = pmcid.removeprefix("PMC")
    if (
        observed_pmid != document.pmid
        or (observed_pmc and observed_pmc.removeprefix("PMC") != expected_number)
        or (identifiers.get("doi") and document.doi
            and identifiers["doi"].casefold() != document.doi.casefold())
    ):
        return PmcFullText(
            document_id=document.document_id, pmid=document.pmid, pmcid=pmcid,
            status="identity_mismatch", retrieved_at=now,
            limitations=("PMC identity disagrees with the requested PubMed record.",),
        )
    body = article.find("body")
    digest = hashlib.sha256(xml).hexdigest()
    if body is None:
        return PmcFullText(
            document_id=document.document_id, pmid=document.pmid, pmcid=pmcid,
            status="metadata_only", content_sha256=digest, retrieved_at=now,
            limitations=("PMC returned metadata without accessible article body.",),
        )
    passages: list[EvidencePassage] = []
    locations: dict[str, str] = {}
    omitted = 0
    retained_characters = 0

    def retain(text: str, section: str, location: str) -> None:
        nonlocal omitted, retained_characters
        if not text:
            return
        if len(text) > 20_000 or len(passages) >= 160 or retained_characters + len(text) > 120_000:
            omitted += 1
            return
        passage_digest = hashlib.sha256(text.encode()).hexdigest()
        pid = f"{document.document_id}:pmc:{len(passages) + 1}:{passage_digest[:12]}"
        passages.append(EvidencePassage(
            passage_id=pid, document_id=document.document_id, text=text,
            section=section, char_start=0, char_end=len(text), content_sha256=passage_digest,
        ))
        locations[pid] = location
        retained_characters += len(text)

    def visit(node: ET.Element, headings: tuple[str, ...], path: str) -> None:
        titles = (*headings, _text(node.find("title"))) if node.tag == "sec" else headings
        titles = tuple(title for title in titles if title)
        counts: dict[str, int] = {}
        for child in node:
            counts[child.tag] = counts.get(child.tag, 0) + 1
            child_path = f"{path}/{child.tag}[{counts[child.tag]}]"
            if child.tag == "table-wrap":
                retain(_table_text(child), "FULL_TEXT/TABLE/" + " > ".join(titles), child_path)
            elif child.tag == "p":
                retain(_text(child), "FULL_TEXT/" + " > ".join(titles), child_path)
            elif child.tag not in {"ref-list", "supplementary-material", "fig", "title"}:
                visit(child, titles, child_path)

    visit(body, (), "article/body")
    floating = article.find("floats-group")
    if floating is not None:
        visit(floating, (), "article/floats-group")
    limitations = [
        "Supplementary files and figures were not fetched; inaccessible details remain unresolved."
    ]
    if omitted:
        limitations.append(f"{omitted} complete source blocks exceeded bounded full-text limits.")
    return PmcFullText(
        document_id=document.document_id, pmid=document.pmid, pmcid=pmcid,
        status="available", content_sha256=digest, retrieved_at=now,
        passages=tuple(passages), locations=locations, limitations=tuple(limitations),
        omitted_blocks=omitted,
    )


class PmcFullTextAdapter:
    """Use ELink/EFetch only; no redirects, publisher crawling or arbitrary URLs."""

    def __init__(self, pubmed: PubMedAdapter, *, cache: QueryCache | None = None,
                 cache_ttl_seconds: int = 21_600) -> None:
        self._pubmed = pubmed
        self._cache = cache
        self._ttl = cache_ttl_seconds
        self.discovery_requests = 0

    async def discover(self, query: str) -> tuple[str, ...]:
        """Find up to five PMC full-text candidates and map to exact PubMed IDs."""
        digest = hashlib.sha256(query.encode()).hexdigest()
        key = f"pmc:discovery:{VERSION}:{digest}"
        if self._cache is not None:
            cached = await self._cache.get(key)
            if cached:
                try:
                    values = json.loads(cached)
                    if isinstance(values, list) and all(isinstance(v, str) and v.isdigit()
                                                       for v in values):
                        return tuple(values)
                except ValueError:
                    pass
        self.discovery_requests += 1
        response = await self._pubmed._request("esearch.fcgi", {
            "db": "pmc", "term": query, "retmode": "json", "retmax": "5", "sort": "relevance",
        })
        try:
            identifiers = response.json()["esearchresult"]["idlist"]
            if (not isinstance(identifiers, list)
                    or any(not str(i).isdigit() for i in identifiers)):
                raise ValueError("Invalid PMC identifier list")
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise RetrievalError("malformed_response") from exc
        if not identifiers:
            return ()
        self.discovery_requests += 1
        response = await self._pubmed._request("elink.fcgi", {
            "dbfrom": "pmc", "db": "pubmed", "linkname": "pmc_pubmed",
            "id": ",".join(str(i) for i in identifiers[:5]), "retmode": "json",
        })
        try:
            linksets = response.json()["linksets"]
            if not isinstance(linksets, list):
                raise ValueError("Invalid PMC link sets")
            values = tuple(dict.fromkeys(
                str(value) for linkset in linksets
                for bundle in linkset.get("linksetdbs", [])
                if bundle.get("dbto") == "pubmed" and bundle.get("linkname") == "pmc_pubmed"
                for value in bundle.get("links", []) if str(value).isdigit()
            ))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise RetrievalError("malformed_response") from exc
        if self._cache is not None:
            await self._cache.set(key, json.dumps(values), self._ttl)
        return values

    async def fetch(self, document: PubMedDocument) -> PmcFullText:
        if not document.pmid.isdigit():
            return PmcFullText(
                document_id=document.document_id, pmid=document.pmid, status="unavailable",
                retrieved_at=datetime.now(UTC), limitations=("Full text requires an exact PMID.",),
            )
        key = f"pmc:fulltext:{VERSION}:{document.pmid}:{document.content_sha256}"
        if self._cache is not None:
            cached = await self._cache.get(key)
            if cached:
                try:
                    result = PmcFullText.model_validate_json(cached)
                    if result.document_id == document.document_id and result.pmid == document.pmid:
                        return result.model_copy(update={"cache_hit": True, "source_requests": 0})
                except ValueError:
                    pass
        requests = 0
        try:
            requests += 1
            response = await self._pubmed._request("elink.fcgi", {
                "dbfrom": "pubmed", "db": "pmc", "linkname": "pubmed_pmc",
                "id": document.pmid, "retmode": "json",
            })
            data = response.json()
            links = [str(value) for linkset in data.get("linksets", [])
                     if document.pmid in [str(value) for value in linkset.get("ids", [])]
                     for bundle in linkset.get("linksetdbs", [])
                     if bundle.get("dbto") == "pmc" and bundle.get("linkname") == "pubmed_pmc"
                     for value in bundle.get("links", []) if str(value).isdigit()]
            if len(set(links)) != 1:
                result = PmcFullText(
                    document_id=document.document_id, pmid=document.pmid,
                    status="not_in_pmc" if not links else "unavailable",
                    retrieved_at=datetime.now(UTC), source_requests=requests,
                    limitations=("No unique accessible PMC article maps to this PMID.",),
                )
            else:
                pmcid = "PMC" + links[0]
                requests += 1
                response = await self._pubmed._request("efetch.fcgi", {
                    "db": "pmc", "id": links[0], "retmode": "xml",
                })
                result = parse_pmc_xml(response.content, document, pmcid).model_copy(update={
                    "source_requests": requests,
                })
        except (RetrievalError, ValueError, TypeError, KeyError, AttributeError):
            result = PmcFullText(
                document_id=document.document_id, pmid=document.pmid, status="unavailable",
                retrieved_at=datetime.now(UTC), source_requests=requests,
                limitations=("Official PMC lookup failed; abstract evidence is retained.",),
            )
        if self._cache is not None and result.status in {
            "available", "not_in_pmc", "metadata_only",
        }:
            await self._cache.set(key, result.model_dump_json(), self._ttl)
        return result
