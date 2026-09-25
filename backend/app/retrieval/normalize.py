"""Normalize official PubMed EFetch XML without inventing missing fields."""

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime

from app.retrieval.errors import RetrievalError
from app.retrieval.integrity import pubmed_integrity, pubmed_reference
from app.retrieval.models import AbstractSection, PubMedDocument, PubMedFetchResult


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = "".join(element.itertext()).strip()
    return value or None


def _date(article: ET.Element) -> date | None:
    for path in (".//ArticleDate", ".//JournalIssue/PubDate", ".//DateCompleted"):
        node = article.find(path)
        if node is None:
            continue
        year_text = _text(node.find("Year"))
        if year_text is None:
            medline_date = _text(node.find("MedlineDate"))
            match = re.search(r"\b(?:19|20)\d{2}\b", medline_date or "")
            year_text = match.group() if match else None
        if year_text is None:
            continue
        month_text = _text(node.find("Month")) or "1"
        month_names = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        month = (
            int(month_text) if month_text.isdigit()
            else month_names.get(month_text[:3].lower(), 1)
        )
        day_text = _text(node.find("Day")) or "1"
        try:
            return date(int(year_text), month, int(day_text))
        except ValueError:
            continue
    return None


def parse_pubmed_xml(
    xml: bytes, *, retrieved_at: datetime | None = None
) -> tuple[PubMedDocument, ...]:
    """Read documents for callers that do not need fetch diagnostics."""

    return parse_pubmed_xml_details(xml, retrieved_at=retrieved_at).documents


def parse_pubmed_xml_details(
    xml: bytes, *, retrieved_at: datetime | None = None
) -> PubMedFetchResult:
    """Parse bounded EFetch output and distinguish absent from incomplete records."""

    # PubMed's official XML includes a DTD declaration. ElementTree does not
    # fetch external DTDs; reject entity definitions to prevent expansion.
    if b"<!ENTITY" in xml.upper():
        raise RetrievalError("malformed_response")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise RetrievalError("malformed_response") from exc
    if root.tag != "PubmedArticleSet":
        raise RetrievalError("malformed_response")
    now = retrieved_at or datetime.now(UTC)
    documents: list[PubMedDocument] = []
    seen: list[str] = []
    incomplete: list[str] = []
    unsupported: list[str] = []
    for record in root.findall("PubmedArticle"):
        citation = record.find("MedlineCitation")
        article = citation.find("Article") if citation is not None else None
        pmid = _text(citation.find("PMID")) if citation is not None else None
        title = _text(article.find("ArticleTitle")) if article is not None else None
        if pmid and pmid.isdigit():
            seen.append(pmid)
        if not pmid or not pmid.isdigit() or not title or article is None:
            if pmid and pmid.isdigit():
                incomplete.append(pmid)
            continue
        abstract_node = article.find("Abstract")
        sections = tuple(
            AbstractSection(label=part.get("Label") or part.get("NlmCategory"), text=value)
            for part in (abstract_node.findall("AbstractText") if abstract_node is not None else [])
            if (value := _text(part)) is not None
        )
        abstract = "\n".join(section.text for section in sections) or None
        authors = tuple(
            name for author in article.findall("AuthorList/Author")
            if (name := " ".join(filter(None, (
                _text(author.find("ForeName")), _text(author.find("LastName"))
            ))))
        )
        doi = next((value for item in record.findall(".//ArticleIdList/ArticleId")
                    if item.get("IdType") == "doi" and (value := _text(item))), None)
        if doi is None:
            doi = next((value for item in article.findall("ELocationID")
                        if item.get("EIdType") == "doi" and (value := _text(item))), None)
        publication_types = tuple(filter(None, (
            _text(item) for item in article.findall("PublicationTypeList/PublicationType")
        )))
        correction_nodes = citation.findall("CommentsCorrectionsList/CommentsCorrections") if (
            citation is not None
        ) else []
        references = tuple(
            reference for node in correction_nodes
            if (reference := pubmed_reference(node.get("RefType") or "",
                                               _text(node.find("PMID")) or "")) is not None
        )
        integrity = pubmed_integrity(
            publication_types, references,
            metadata_present=(article.find("PublicationTypeList") is not None
                              or (citation is not None and
                                  citation.find("CommentsCorrectionsList") is not None)),
            checked_at=now,
        )
        mesh_terms = tuple(filter(None, (
            _text(item) for item in record.findall("MedlineCitation/MeshHeadingList/"
                                                  "MeshHeading/DescriptorName")
        )))
        journal = _text(article.find("Journal/Title"))
        language = _text(article.find("Language"))
        published = _date(article)
        content = {
            "pmid": pmid, "title": title, "abstract": abstract,
            "sections": [section.model_dump() for section in sections],
            "journal": journal, "date": published.isoformat() if published else None,
            "authors": authors, "doi": doi, "publication_types": publication_types,
            "mesh_terms": mesh_terms, "language": language,
            "integrity_types": publication_types,
            "integrity_references": [ref.model_dump(mode="json") for ref in references],
        }
        content_sha256 = hashlib.sha256(
            json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            .encode("utf-8")
        ).hexdigest()
        documents.append(PubMedDocument(
            document_id=f"pubmed:{pmid}", pmid=pmid, title=title,
            abstract=abstract, abstract_sections=sections, journal=journal,
            publication_date=published, authors=authors, doi=doi,
            publication_types=publication_types, mesh_terms=mesh_terms,
            language=language, canonical_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            retrieved_at=now, content_sha256=content_sha256,
            integrity=integrity, metadata_provenance={
                "title": "pubmed", "doi": "pubmed" if doi else "absent",
                "publication_date": "pubmed" if published else "absent",
                "publication_types": "pubmed", "abstract": "pubmed" if abstract else "absent",
            },
        ))
    for record in root.findall("PubmedBookArticle"):
        pmid = _text(record.find("BookDocument/PMID"))
        if pmid and pmid.isdigit():
            seen.append(pmid)
            unsupported.append(pmid)
    return PubMedFetchResult(
        documents=tuple(documents), seen_pmids=tuple(seen),
        incomplete_pmids=tuple(incomplete), unsupported_pmids=tuple(unsupported),
    )
