"""Append new retrieval records and frozen snapshots; never rewrite old packs."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import EvidenceDocument
from app.models.evidence import EvidencePassage as EvidencePassageRow
from app.models.retrieval import (
    EvidencePackRecord,
    RetrievalDocumentQuery,
    RetrievalQuery,
    RetrievalRun,
)
from app.retrieval.models import RetrievalResult


def persist_retrieval(session: Session, result: RetrievalResult) -> EvidencePackRecord:
    """Persist a run, query/document provenance, and an immutable JSON snapshot."""

    pack = result.pack
    run = RetrievalRun(
        id=uuid4(), claim_id=pack.claim_id, source="pubmed",
        status=result.diagnostics.status,
        query_plan_json=pack.query_plan.model_dump(mode="json"),
        diagnostics_json=result.diagnostics.model_dump(mode="json"),
        retrieved_at=pack.retrieved_at,
    )
    try:
        session.add(run)
        session.flush()
        query_rows: dict[str, RetrievalQuery] = {}
        executions = {execution.query_id: execution for execution in result.query_executions}
        for query in pack.query_plan.queries:
            execution = executions[query.query_id]
            row = RetrievalQuery(
                id=uuid4(), run_id=run.id, query_id=query.query_id,
                family=query.family, query_text=query.query,
                source_fields=list(query.source_fields),
                result_count=len(execution.pmids), cache_hit=execution.cache_hit,
            )
            session.add(row)
            query_rows[query.query_id] = row
        session.flush()
        document_rows: dict[str, EvidenceDocument] = {}
        for document in pack.documents:
            document_row = session.scalar(select(EvidenceDocument).where(
                EvidenceDocument.source_kind == "pubmed",
                EvidenceDocument.pmid == document.pmid,
                EvidenceDocument.content_sha256 == document.content_sha256,
            ))
            if document_row is None:
                document_row = EvidenceDocument(
                    id=uuid4(), source_kind="pubmed", source_tier=None,
                    canonical_url=document.canonical_url, pmid=document.pmid, doi=document.doi,
                    title=document.title, abstract=document.abstract,
                    abstract_sections=[section.model_dump(mode="json")
                                       for section in document.abstract_sections],
                    journal=document.journal, authors=list(document.authors),
                    publication_types=list(document.publication_types),
                    mesh_terms=list(document.mesh_terms), language=document.language,
                    published_at=document.publication_date, retrieved_at=document.retrieved_at,
                    retraction_status="unknown", license_code=None,
                    content_sha256=document.content_sha256,
                )
                session.add(document_row)
                session.flush()
            document_rows[document.document_id] = document_row
            for query_id in document.query_ids:
                session.add(RetrievalDocumentQuery(
                    document_id=document_row.id, query_id=query_rows[query_id].id,
                ))
        for ranked in pack.passages:
            passage = ranked.passage
            document_row = document_rows[passage.document_id]
            existing = session.scalar(select(EvidencePassageRow).where(
                EvidencePassageRow.document_id == document_row.id,
                EvidencePassageRow.section == passage.section,
                EvidencePassageRow.snippet_sha256 == passage.content_sha256,
            ))
            if existing is None:
                session.add(EvidencePassageRow(
                    id=uuid4(), document_id=document_row.id, section=passage.section,
                    char_start=passage.char_start, char_end=passage.char_end,
                    snippet=passage.text, snippet_sha256=passage.content_sha256,
                ))
        record = EvidencePackRecord(
            id=uuid4(), claim_id=pack.claim_id, run_id=run.id,
            version=pack.evidence_pack_version, snapshot_hash=pack.snapshot_hash,
            snapshot_json=pack.model_dump(mode="json"), created_at=datetime.now(UTC),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record
    except Exception:
        session.rollback()
        raise
