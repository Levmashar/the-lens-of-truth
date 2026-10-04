"""PostgreSQL authoritative version round trip; offline and rolled back."""

import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_reliability_slice3 import HTML, NOW, claim, pack_for, source

from app.adapters.authoritative import freeze_html
from app.db.session import SessionLocal
from app.models.claim import Claim
from app.models.enums import InputType
from app.models.evidence import EvidenceDocument, EvidencePassage
from app.models.submission import Submission
from app.retrieval.models import QueryExecution, RetrievalDiagnostics, RetrievalResult
from app.retrieval.persistence import persist_retrieval


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Requires migrated PostgreSQL")
def test_authoritative_versions_preserve_prior_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = claim()
    with SessionLocal() as session:
        monkeypatch.setattr(session, "commit", session.flush)
        try:
            submission = Submission(
                id=uuid4(),
                client="test",
                language="en",
                input_type=InputType.TEXT,
                content_sha256="a" * 64,
                privacy_notice_version="fixture",
                consent_accepted=True,
                purge_after=NOW + timedelta(hours=1),
            )
            session.add(submission)
            session.flush()
            session.add(
                Claim(
                    id=snapshot.claim_id,
                    submission_id=submission.id,
                    ordinal=1,
                    raw_text=snapshot.raw_text,
                    coreference_uncertain=False,
                )
            )
            session.flush()
            records = []
            long_heading = "Reviewed methods and limitations " * 6
            fixture = HTML.replace("<h2>Methods</h2>", f"<h2>{long_heading}</h2>")
            for html in (fixture, fixture.replace("limitations", "new limitations")):
                pack = pack_for((freeze_html(source(), html, now=NOW),), snapshot)
                result = RetrievalResult(
                    pack=pack,
                    diagnostics=RetrievalDiagnostics(
                        status="ok", query_count=len(pack.query_plan.queries), documents_returned=1
                    ),
                    query_executions=tuple(
                        QueryExecution(query_id=q.query_id, pmids=(), cache_hit=False)
                        for q in pack.query_plan.queries
                    ),
                )
                records.append(persist_retrieval(session, result))
            first = records[0].snapshot_json.copy()
            assert records[0].snapshot_hash != records[1].snapshot_hash
            session.expire_all()
            assert records[0].snapshot_json == first
            rows = list(
                session.scalars(
                    select(EvidenceDocument).where(
                        EvidenceDocument.canonical_url == source().canonical_url
                    )
                )
            )
            assert len(rows) == 2
            assert all(
                r.pmid is None and r.source_kind == "authoritative_public_health" for r in rows
            )
            passages = list(session.scalars(select(EvidencePassage).where(
                EvidencePassage.document_id.in_([r.id for r in rows]))))
            assert max(len(p.section or "") for p in passages) > 128
        finally:
            session.rollback()
