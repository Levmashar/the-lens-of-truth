"""Optional PostgreSQL integration check; no live PubMed, transaction rolled back."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.claim import Claim
from app.models.enums import InputType
from app.models.evidence import EvidenceDocument, EvidencePassage
from app.models.retrieval import (
    EvidencePackRecord,
    RetrievalDocumentQuery,
    RetrievalQuery,
    RetrievalRun,
)
from app.models.submission import Submission
from app.pipeline.pico import NormalizedPico
from app.retrieval.evidence_pack import build_evidence_pack
from app.retrieval.models import (
    ClaimSnapshot,
    QueryExecution,
    RetrievalDiagnostics,
    RetrievalResult,
)
from app.retrieval.normalize import parse_pubmed_xml
from app.retrieval.passages import extract_passages
from app.retrieval.persistence import persist_retrieval
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import rank_passages

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1",
                                reason="Set RUN_DB_TESTS=1 with migrated PostgreSQL")
XML = (Path(__file__).parent / "fixtures" / "pubmed_sample.xml").read_bytes()


def test_retrieval_run_pack_and_query_provenance_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim_id, submission_id = uuid4(), uuid4()
    raw = "Frequent sunscreen use causes invasive melanoma."
    pico = NormalizedPico(
        original_claim=raw, intervention_or_exposure="Frequent sunscreen use",
        outcome="invasive melanoma", claim_type="causal",
    )
    snapshot = ClaimSnapshot(claim_id=claim_id, raw_text=raw, claim_type="causal", pico=pico)
    plan = plan_pubmed_queries(snapshot)
    document = parse_pubmed_xml(XML)[0].model_copy(update={
        "query_ids": tuple(query.query_id for query in plan.queries),
    })
    ranked = rank_passages(snapshot, (document,), extract_passages(document))
    pack = build_evidence_pack(snapshot, plan, (document,), ranked)
    result = RetrievalResult(
        pack=pack,
        diagnostics=RetrievalDiagnostics(
            status="ok", query_count=len(plan.queries), pmids_found=1,
            documents_returned=1,
        ),
        query_executions=tuple(QueryExecution(
            query_id=query.query_id, pmids=(document.pmid,), cache_hit=False,
        ) for query in plan.queries),
    )
    with SessionLocal() as session:
        try:
            session.add(Submission(
                id=submission_id, client="api", language="en", input_type=InputType.TEXT,
                content_sha256="a" * 64, privacy_notice_version="test",
                consent_accepted=True, status="claims_extracted",
                purge_after=datetime.now(UTC) + timedelta(hours=1),
            ))
            session.add(Claim(
                id=claim_id, submission_id=submission_id, ordinal=1, raw_text=raw,
                claim_type="causal", risk_class="standard", coreference_uncertain=False,
                normalization_status="normalized", pico_json=pico.model_dump(mode="json"),
            ))
            session.flush()
            monkeypatch.setattr(session, "commit", session.flush)
            record = persist_retrieval(session, result)
            assert isinstance(record, EvidencePackRecord)
            assert record.snapshot_hash == pack.snapshot_hash
            assert record.version == "1.3"
            assert record.snapshot_json["documents"][0]["integrity"]["status"] == "unknown"
            assert session.scalar(select(RetrievalRun).where(
                RetrievalRun.claim_id == claim_id,
            )) is not None
            assert len(list(session.scalars(select(RetrievalQuery).where(
                RetrievalQuery.run_id == record.run_id,
            )))) == len(plan.queries)
            assert session.scalar(select(RetrievalDocumentQuery).join(RetrievalQuery).where(
                RetrievalQuery.run_id == record.run_id,
            )) is not None
            assert session.scalar(select(EvidenceDocument).where(
                EvidenceDocument.pmid == document.pmid,
                EvidenceDocument.content_sha256 == document.content_sha256,
            )) is not None
            assert session.scalar(select(EvidencePassage).where(
                EvidencePassage.snippet_sha256 == ranked[0].passage.content_sha256,
            )) is not None
        finally:
            session.rollback()
