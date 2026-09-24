"""Extract exact title and abstract-section passages, never full text."""

import hashlib

from app.retrieval.models import EvidencePassage, PubMedDocument


def extract_passages(document: PubMedDocument) -> tuple[EvidencePassage, ...]:
    passages: list[EvidencePassage] = []
    sources = [("TITLE", document.title)]
    sources.extend((section.label or "ABSTRACT", section.text)
                   for section in document.abstract_sections)
    for index, (section, text) in enumerate(sources):
        if not text:
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        passages.append(EvidencePassage(
            passage_id=f"{document.document_id}:{index}:{digest[:12]}",
            document_id=document.document_id, text=text, section=section,
            char_start=0, char_end=len(text), content_sha256=digest,
        ))
    return tuple(passages)
