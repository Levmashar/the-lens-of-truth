"""Test-environment-only full-chain synthetic fixture; never a medical evaluation."""

import argparse
import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.judging.models import EvidenceSufficiency, JudgeDecision, JudgeLabel, JudgeRun
from app.judging.prompt import PROMPT_VERSION, prepare_judge_input
from app.models.claim import Claim
from app.models.enums import InputType
from app.models.report_run import ReportRunRecord
from app.models.submission import Submission
from app.orchestration.service import AnalysisOrchestrator
from app.orchestration.state import claim_runs, start_analysis
from app.pipeline.claim_types import ClaimType
from app.pipeline.pico import NormalizedPico
from app.report.models import LensReport
from app.retrieval.evidence_pack import build_evidence_pack
from app.retrieval.models import (
    AbstractSection,
    ClaimSnapshot,
    DocumentIntegrity,
    EvidencePack,
    PubMedDocument,
    QueryExecution,
    RetrievalDiagnostics,
    RetrievalResult,
)
from app.retrieval.passages import extract_passages
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import rank_passages
from app.schemas.analysis import AnalysisInput, Consent, CreateAnalysisRequest
from app.validation.models import (
    CitationValidation,
    EntailmentStatus,
    JudgeValidationResult,
    JudgeValidationRun,
    NumericAlignment,
    RelationAlignment,
    ScopeAlignment,
    ValidationStatus,
)
from app.verdict.models import AggregationMode
from app.verdict.policy import POLICY_V1

FIXTURE_TEXT = "Treatment X reduces Y in adults."


@dataclass
class FixtureIngestion:
    """Offline supplied extraction/normalization; not an AI or terminology adapter."""

    claims: tuple[str, ...]

    async def create_analysis(
        self, *, session: Session, request: CreateAnalysisRequest,
        analysis_id: UUID | None = None,
    ) -> Submission:
        assert request.input.type == "text" and request.input.text is not None
        source = request.input.text
        submission = Submission(
            id=analysis_id or uuid4(), client=request.client, language=request.language,
            input_type=InputType.TEXT, content_sha256=hashlib.sha256(source.encode()).hexdigest(),
            privacy_notice_version=request.consent.privacy_notice_version,
            consent_accepted=True, status="claims_extracted",
            extraction_provider="synthetic_fixture", extraction_model=None,
            purge_after=datetime.now(UTC) + timedelta(hours=1),
        )
        next_offset = 0
        for ordinal, text in enumerate(self.claims, start=1):
            offset = source.find(text, next_offset)
            if offset < 0:
                raise ValueError("Fixture claim must be an exact source span")
            next_offset = offset + len(text)
            match = re.fullmatch(r"Treatment ([A-Z]) reduces ([A-Z]) in adults\.", text)
            if match is None:
                raise ValueError("Unsupported synthetic fixture claim")
            exposure, outcome = f"Treatment {match.group(1)}", match.group(2)
            pico = NormalizedPico(
                original_claim=text, population="adults",
                intervention_or_exposure=exposure, outcome=outcome,
                claim_type=ClaimType.TREATMENT,
            )
            submission.claims.append(Claim(
                id=uuid4(), ordinal=ordinal, span_start=offset,
                span_end=offset + len(text), raw_text=text, claim_type="treatment",
                population="adults", intervention_or_exposure=exposure, outcome=outcome,
                pico_json=pico.model_dump(mode="json"), linked_entities=[],
                normalization_status="normalized", risk_class="standard",
                coreference_uncertain=False,
            ))
        session.add(submission)
        session.commit()
        session.refresh(submission)
        return submission


async def fixture_retrieval(
    claim: ClaimSnapshot, *, contradicted: bool = False, no_results: bool = False,
) -> RetrievalResult:
    """One conspicuously synthetic source; never call PubMed or Crossref."""

    plan = plan_pubmed_queries(claim)
    if no_results:
        return RetrievalResult(
            pack=build_evidence_pack(claim, plan, (), ()),
            diagnostics=RetrievalDiagnostics(status="no_results", query_count=len(plan.queries)),
            query_executions=tuple(QueryExecution(
                query_id=query.query_id, pmids=(), cache_hit=False,
            ) for query in plan.queries),
        )
    exposure = claim.pico.intervention_or_exposure if claim.pico else None
    outcome = claim.pico.outcome if claim.pico else None
    if exposure is None or outcome is None:
        raise ValueError("Synthetic fixture needs exact PICO fields")
    relation = "did not reduce" if contradicted else "reduced"
    passage_text = (f"In adults, {exposure} {relation} {outcome} compared with placebo "
                    "in this SYNTHETIC TEST EVIDENCE fixture.")
    fixture_pmid = str(90_000_000 + claim.claim_id.int % 9_000_000)
    document = PubMedDocument(
        document_id=f"fixture:{claim.claim_id}", pmid=fixture_pmid,
        title=f"SYNTHETIC TEST EVIDENCE: {exposure} and {outcome}",
        abstract=passage_text,
        abstract_sections=(AbstractSection(label="RESULTS", text=passage_text),),
        canonical_url="https://example.invalid/synthetic-evidence",
        retrieved_at=datetime.now(UTC),
        content_sha256=hashlib.sha256(passage_text.encode()).hexdigest(),
        query_ids=(plan.queries[0].query_id,),
        study_design="randomized_controlled_trial",
        integrity=DocumentIntegrity(status="valid"),
    )
    documents = (document,)
    passages = tuple(extract_passages(document))
    pack = build_evidence_pack(
        claim, plan, documents, rank_passages(claim, documents, passages),
    )
    return RetrievalResult(
        pack=pack,
        diagnostics=RetrievalDiagnostics(
            status="ok", query_count=len(plan.queries), pmids_found=1,
            documents_returned=1,
        ),
        query_executions=tuple(QueryExecution(
            query_id=query.query_id,
            pmids=(document.pmid,) if query.query_id == plan.queries[0].query_id else (),
            cache_hit=False,
        ) for query in plan.queries),
    )


async def fixture_judges(
    pack_id: UUID, pack: EvidencePack, *, unavailable: bool = False,
    label: JudgeLabel = JudgeLabel.SUPPORTED,
) -> tuple[JudgeRun, ...]:
    if unavailable:
        return ()
    prepared = prepare_judge_input(pack_id, pack)
    now = datetime.now(UTC)
    decision = JudgeDecision(
        schema_version="1.0", label=label,
        cited_evidence_ids=pack.selected_evidence_ids[:1], opposing_evidence_ids=(),
        reasoning_summary="The synthetic fixture passage states this result.",
        claim_strength_assessed="synthetic fixture scope",
        evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
        uncertainty_reasons=(),
    )
    return tuple(JudgeRun(
        judge_run_id=uuid4(), claim_id=pack.claim_id, evidence_pack_id=pack_id,
        evidence_pack_hash=pack.snapshot_hash, slot=slot, provider="synthetic_fixture",
        model=f"fixture-{slot}", model_family=f"fixture-family-{slot}",
        model_snapshot=f"fixture-snapshot-{slot}", model_identity_verified=True,
        model_family_verified=True, search_isolation_verified=True,
        prompt_version=PROMPT_VERSION, prompt_hash=prepared.prompt_hash,
        requested_at=now, responded_at=now, latency_ms=0, attempt_count=1,
        outcome_status="succeeded", response_json=decision.model_dump(mode="json"),
        decision=decision,
    ) for slot in (1, 2, 3))


async def fixture_validation(judge: JudgeRun, pack: EvidencePack) -> JudgeValidationRun:
    """Explicit known synthetic validation, not a live entailment claim."""

    assert judge.decision is not None
    now = datetime.now(UTC)
    citation = CitationValidation(
        evidence_id=judge.decision.cited_evidence_ids[0], role="cited", exists=True,
        selected_for_judging=True, passage_hash_matches=True,
        document_provenance_exists=True, integrity_status="valid",
        numeric_alignment=NumericAlignment.ALIGNED,
        scope_alignment=ScopeAlignment.ALIGNED,
        relation_alignment=RelationAlignment.ALIGNED,
        entailment_status=EntailmentStatus.ENTAILS_JUDGE_USE,
        issue_codes=(),
    )
    result = JudgeValidationResult(
        judge_run_id=judge.judge_run_id, evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=pack.snapshot_hash, judge_label=judge.decision.label,
        citation_validations=(citation,), opposing_citation_validations=(),
        validation_status=ValidationStatus.VALIDATED,
        fatal_issue_codes=(), warnings=(),
        validation_version=POLICY_V1.validation_version,
    )
    return JudgeValidationRun(
        id=uuid4(), judge_run_id=judge.judge_run_id,
        evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=pack.snapshot_hash,
        validation_version=POLICY_V1.validation_version,
        deterministic_validator_version="synthetic_fixture",
        entailment_provider="fixture", entailment_model="fixture",
        prompt_version="fixture", prompt_hash="f" * 64,
        started_at=now, completed_at=now, status=ValidationStatus.VALIDATED,
        result=result, error_category=None, latency_ms=0, attempt_count=1,
    )


async def smoke(text: str, *, unavailable: bool = False) -> UUID:
    settings = get_settings()
    if settings.app_env != "test":
        raise SystemExit("Synthetic fixture smoke requires APP_ENV=test.")
    if text != FIXTURE_TEXT:
        raise SystemExit(f"Only this synthetic fixture claim is accepted: {FIXTURE_TEXT}")
    request = CreateAnalysisRequest(
        client="api", input=AnalysisInput(type="text", text=text),
        consent=Consent(privacy_notice_version="fixture", accepted=True),
    )
    async def judges(pack_id: UUID, pack: EvidencePack) -> tuple[JudgeRun, ...]:
        return await fixture_judges(pack_id, pack, unavailable=unavailable)

    orchestrator = AnalysisOrchestrator(
        ingestion=FixtureIngestion((text,)), retrieve=fixture_retrieval,
        judge=judges, validate=fixture_validation,
        mode=AggregationMode.FIXTURE_OR_EVALUATION,
    )
    with SessionLocal() as session:
        run, _ = start_analysis(session, request, idempotency_key=None, retention_hours=1)
        await orchestrator.run(session, run.id, request)
        session.refresh(run)
        rows = claim_runs(session, run.id)
        print("SYNTHETIC OFFLINE FIXTURE — NOT MEDICAL EVIDENCE")
        print(f"ANALYSIS\nid: {run.id}\nstatus: {run.status}")
        for row in rows:
            print(f"CLAIMS\n{row.ordinal}: {text}")
            print("PIPELINE")
            for stage in ("extracting", "normalizing", "retrieving", "judging",
                          "validating", "aggregating", "building_report"):
                done = stage in run.completed_stages or stage in row.completed_stages
                print(f"{stage:17} {'complete' if done else 'incomplete'}")
            print("ARTIFACTS")
            print(f"pack: {row.evidence_pack_id}\njudges: {row.judge_run_ids}")
            print(f"validations: {row.validation_run_ids}")
            print(f"verdict: {row.verdict_run_id}\nreport: {row.report_run_id}")
            if row.report_run_id:
                report_row = session.get(ReportRunRecord, row.report_run_id)
                assert report_row is not None
                report = LensReport.model_validate(report_row.result_json)
                print("FINAL INTERNAL REPORT")
                print(f"{report.verdict_display}: {report.short_summary}")
                print(f"PRODUCTION QUALIFIED: {str(report.production_qualified).lower()}")
        return run.id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one synthetic offline orchestration fixture")
    parser.add_argument("--text", default=FIXTURE_TEXT)
    parser.add_argument("--unavailable", action="store_true",
                        help="Simulate unavailable judges and an Unable result")
    args = parser.parse_args()
    asyncio.run(smoke(args.text, unavailable=args.unavailable))


if __name__ == "__main__":
    main()
