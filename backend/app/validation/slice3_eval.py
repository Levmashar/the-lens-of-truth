"""Opt-in paired coverage evaluation; explicit PICO, unchanged live stage callbacks.

Fetch PubMed once per claim, freeze a PubMed-only baseline and a combined pack
from those SAME records. Both run the existing judge/validation/revision/verdict/
report callbacks. This is an engineer-authored development test, not clinical review.
"""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any, Literal, cast
from uuid import uuid4

from app.core.config import get_settings
from app.core.debug_trace import model_events, trace_analysis, trace_claim
from app.core.diagnostics import diagnostic_secrets, sanitize_diagnostic
from app.db.session import SessionLocal
from app.dependencies import build_entity_linker, get_authoritative_adapter
from app.judging.prompt import prepare_judge_input
from app.models.analysis_run import AnalysisRunRecord, ClaimAnalysisRunRecord
from app.models.claim import Claim
from app.models.enums import InputType
from app.models.submission import Submission
from app.orchestration.worker import build_orchestrator
from app.pipeline.claim_types import ClaimType
from app.pipeline.pico import normalize_stored_pico
from app.retrieval.claims import snapshot_claim
from app.retrieval.evidence_pack import build_evidence_pack
from app.retrieval.models import (
    ClaimSnapshot,
    EvidencePack,
    QueryExecution,
    RetrievalDiagnostics,
    RetrievalResult,
)
from app.retrieval.passages import extract_passages
from app.retrieval.ranking import rank_passages
from app.retrieval.study_quality import annotate_study_quality
from app.validation.evaluation_budget import EvaluationBudget
from app.validation.replay import capture

CASES = (
    ("Smoking causes lung cancer.", "Smoking", "lung cancer", "causal"),
    ("Frequent smoking causes lung cancer.", "Frequent smoking", "lung cancer", "causal"),
    (
        "Frequent sunscreen use causes invasive melanoma.",
        "Frequent sunscreen use",
        "invasive melanoma",
        "causal",
    ),
    ("High blood pressure causes stroke.", "High blood pressure", "stroke", "causal"),
    ("Vitamin C prevents the common cold.", "Vitamin C", "common cold", "prevention"),
    ("Carrots improve eyesight.", "Carrots", "eyesight", "causal"),
)


async def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Development/test only")
    adapter = get_authoritative_adapter(settings)
    if adapter is None:
        raise SystemExit("Enable the approved-source adapter; configuration was NOT changed")
    budget = EvaluationBudget(args.max_calls, args.deadline)
    output: dict[str, Any] = {
        "version": "slice3-coverage-1.0",
        "human_reviewed": False,
        "origin": "engineer-authored source-grounded retrieval controls",
        "production_qualified": False,
        "configuration_changed": False,
        "paired_pubmed_content": True,
        "cases": [],
        "cost_usd": None,
        "cost_note": "No reliable billing rates returned; report token usage only",
    }
    pilot = json.loads(args.pilot.read_text(encoding="utf-8")) if args.pilot else None
    output["pilot_reference"] = args.pilot.name if args.pilot else None
    try:
        with budget.measure():
            async with asyncio.timeout(args.deadline):
                for index, (text, exposure, outcome, kind) in enumerate(CASES[: args.limit], 1):
                    pico = normalize_stored_pico(
                        raw_text=text,
                        claim_type=ClaimType(kind),
                        population=None,
                        intervention_or_exposure=exposure,
                        comparator=None,
                        outcome=outcome,
                        timeframe=None,
                    )
                    entities = build_entity_linker(settings).link(pico)
                    snapshot = ClaimSnapshot(
                        claim_id=uuid4(),
                        raw_text=text,
                        claim_type=ClaimType(kind),
                        pico=pico,
                        entities=entities,
                    )
                    orchestrator = build_orchestrator(settings)
                    fetch_started = monotonic()
                    # Normal configured retrieval; partition without refetching sources.
                    if pilot:
                        prior_case = pilot["cases"][index - 1]
                        prior = prior_case["variants"][0]
                        original = prior["artifact"]
                        if prior_case["claim"] != text or datetime.fromisoformat(
                            original["purge_after"]
                        ) <= datetime.now(UTC):
                            raise ValueError("Mismatched or expired pilot; do not replay")
                        baseline_pack = EvidencePack.model_validate(
                            original["claims"][0]["pack"]["snapshot_json"]
                        )
                        approved, states = await adapter.retrieve(snapshot)
                        combined_docs = (*baseline_pack.documents, *approved)
                        combined_pack = build_evidence_pack(
                            snapshot,
                            baseline_pack.query_plan,
                            combined_docs,
                            rank_passages(
                                snapshot,
                                combined_docs,
                                tuple(p for d in combined_docs for p in extract_passages(d)),
                            ),
                            selected_limit=settings.pubmed_selected_evidence_limit,
                            max_per_document=settings.pubmed_max_passages_per_document,
                            pack_version="1.5",
                        )
                        diagnostics = RetrievalDiagnostics.model_validate(
                            original["claims"][0]["retrieval"]["diagnostics_json"]
                        )
                        fetched = RetrievalResult(
                            pack=combined_pack,
                            diagnostics=diagnostics.model_copy(
                                update={
                                    "documents_returned": len(combined_docs),
                                    "authoritative_statuses": states,
                                }
                            ),
                            query_executions=tuple(
                                QueryExecution.model_validate(q)
                                for q in prior_case["search_executions"]
                            ),
                        )
                    else:
                        fetched = await orchestrator.retrieve(snapshot)
                    fetch_seconds = round(monotonic() - fetch_started, 3)
                    pubmed = tuple(
                        d.model_copy(update={"relationship_analysis": None})
                        for d in fetched.pack.documents
                        if d.source_kind == "pubmed"
                    )
                    baseline = build_evidence_pack(
                        snapshot,
                        fetched.pack.query_plan,
                        pubmed,
                        rank_passages(
                            snapshot, pubmed, tuple(p for d in pubmed for p in extract_passages(d))
                        ),
                        selected_limit=settings.pubmed_selected_evidence_limit,
                        max_per_document=settings.pubmed_max_passages_per_document,
                    )
                    case: dict[str, Any] = {
                        "number": index,
                        "claim": text,
                        "source_fetch_seconds": fetch_seconds,
                        "search_executions": [
                            q.model_dump(mode="json") for q in fetched.query_executions
                        ],
                        "authoritative_statuses": fetched.diagnostics.authoritative_statuses,
                        "variants": [],
                    }
                    output["cases"].append(case)
                    # Recharacterize identical source records for AFTER, not baseline.
                    after_docs = tuple(
                        annotate_study_quality(snapshot, d) if d.source_kind == "pubmed" else d
                        for d in fetched.pack.documents
                    )
                    after = build_evidence_pack(
                        snapshot,
                        fetched.pack.query_plan,
                        after_docs,
                        rank_passages(
                            snapshot,
                            after_docs,
                            tuple(p for d in after_docs for p in extract_passages(d)),
                        ),
                        selected_limit=settings.pubmed_selected_evidence_limit,
                        max_per_document=settings.pubmed_max_passages_per_document,
                        pack_version="1.5",
                    )
                    variants = (
                        (("combined", after),)
                        if pilot
                        else (("pubmed_only", baseline), ("combined", after))
                    )
                    for name, pack in variants:
                        started = monotonic()
                        call_start = len(budget.calls)
                        analysis_id, submission_id = uuid4(), uuid4()
                        checkpoint = ClaimAnalysisRunRecord(
                            id=uuid4(),
                            analysis_run_id=analysis_id,
                            claim_id=uuid4(),
                            ordinal=1,
                            status="queued",
                            stage="queued",
                            completed_stages=[],
                            stage_timestamps={},
                            judge_run_ids=[],
                            validation_run_ids=[],
                        )
                        # Each variant is a new auditable claim/run, never an overwrite.
                        with SessionLocal() as session:
                            submission = Submission(
                                id=submission_id,
                                client="slice3_eval",
                                language="en",
                                input_type=InputType.TEXT,
                                content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                                privacy_notice_version="developer-test",
                                consent_accepted=True,
                                status="claims_extracted",
                                extraction_provider="manual_source_grounded_eval",
                                purge_after=datetime.now(UTC) + timedelta(hours=1),
                            )
                            claim = Claim(
                                id=checkpoint.claim_id,
                                submission_id=submission_id,
                                ordinal=1,
                                raw_text=text,
                                normalized_text=text,
                                standalone_status="complete",
                                claim_type=kind,
                                intervention_or_exposure=exposure,
                                outcome=outcome,
                                normalization_status="normalized",
                                risk_class="standard",
                                pico_json=pico.model_dump(mode="json"),
                                linked_entities=[e.model_dump(mode="json") for e in entities],
                                coreference_uncertain=False,
                            )
                            analysis = AnalysisRunRecord(
                                id=analysis_id,
                                submission_id=submission_id,
                                request_hash="a" * 64,
                                status="running",
                                stage="normalizing",
                                claim_count=1,
                                completed_claims=0,
                                completed_stages=["extracting"],
                                stage_timestamps={},
                                purge_after=submission.purge_after,
                            )
                            session.add(submission)
                            session.flush()
                            session.add(claim)
                            session.add(analysis)
                            session.flush()
                            session.add(checkpoint)
                            session.commit()
                            variant_snapshot = snapshot_claim(claim)
                            variant_docs = pack.documents
                            variant_pack = build_evidence_pack(
                                variant_snapshot,
                                pack.query_plan,
                                variant_docs,
                                rank_passages(
                                    variant_snapshot,
                                    variant_docs,
                                    tuple(p for d in variant_docs for p in extract_passages(d)),
                                ),
                                selected_limit=settings.pubmed_selected_evidence_limit,
                                max_per_document=settings.pubmed_max_passages_per_document,
                                pack_version=cast(
                                    Literal["1.4", "1.5"], pack.evidence_pack_version
                                ),
                            )
                            frozen_result = RetrievalResult(
                                pack=variant_pack,
                                diagnostics=fetched.diagnostics.model_copy(
                                    update={
                                        "status": "partial_metadata"
                                        if fetched.diagnostics.missing_pmids
                                        else "ok"
                                        if variant_docs
                                        else "no_results",
                                        "documents_returned": len(variant_docs),
                                        "authoritative_statuses": (
                                            fetched.diagnostics.authoritative_statuses
                                        )
                                        if name == "combined"
                                        else {},
                                    }
                                ),
                                query_executions=fetched.query_executions,
                            )

                            async def frozen_retrieval(
                                _: ClaimSnapshot,
                                frozen: RetrievalResult = frozen_result,
                            ) -> RetrievalResult:
                                return frozen

                            orchestrator.retrieve = frozen_retrieval
                            with trace_analysis(analysis_id, enabled=True), trace_claim(claim.id):
                                try:
                                    async with asyncio.timeout(args.variant_deadline):
                                        await orchestrator._run_claim(
                                            session, analysis, checkpoint, claim
                                        )
                                    analysis.status = "completed"
                                    analysis.completed_claims = 1
                                except Exception as exc:
                                    session.rollback()
                                    checkpoint.status = "failed"
                                    checkpoint.failure_code = type(exc).__name__
                                    analysis.status = "failed"
                                analysis.stage = analysis.status
                                session.commit()
                                artifact = capture(session, analysis_id)
                            variant: dict[str, Any] = {
                                "name": name,
                                "analysis_id": str(analysis_id),
                                "latency_seconds": round(monotonic() - started, 3),
                                "http_calls": len(budget.calls) - call_start,
                                "status": analysis.status,
                                "artifact": artifact,
                                "model_events": model_events(analysis_id),
                                "selected": [
                                    {
                                        "evidence_id": p.evidence_id,
                                        "document_id": p.passage.document_id,
                                        "reason": p.selection_reason,
                                    }
                                    for p in variant_pack.passages
                                    if p.selected_for_judging
                                ],
                            }
                            if variant_pack.selected_evidence_ids:
                                prepared = prepare_judge_input(
                                    checkpoint.evidence_pack_id or uuid4(), variant_pack
                                )
                                variant["judge_input"] = prepared.input_snapshot_json
                            case["variants"].append(variant)
                            captured_claim = cast(Any, artifact).get("claims", [{}])[0]
                            verdict = captured_claim.get("verdict") or {}
                            result = verdict.get("result_json") or {}
                            print(
                                json.dumps(
                                    {
                                        "case": index,
                                        "variant": name,
                                        "status": variant["status"],
                                        "qualified": result.get("qualified_judges"),
                                        "verdict": result.get("verdict"),
                                        "seconds": variant["latency_seconds"],
                                        "calls": variant["http_calls"],
                                    }
                                ),
                                flush=True,
                            )
                    if budget.failure:
                        break
    except TimeoutError:
        budget.failure = "evaluation_deadline_exceeded"
    output["budget"] = budget.summary()
    return dict(sanitize_diagnostic(output, diagnostic_secrets(settings)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--max-calls", type=int, default=480)
    parser.add_argument("--deadline", type=float, default=2400)
    parser.add_argument("--variant-deadline", type=float, default=150)
    parser.add_argument("--runtime", type=Path, default=Path("runtime"))
    parser.add_argument(
        "--pilot", type=Path, help="Reuse retained PubMed-only control content; run combined only"
    )
    args = parser.parse_args()
    if not args.run:
        raise SystemExit(
            "Opt in with --run: writes new evaluation rows and uses paid configured APIs"
        )
    if not (
        1 <= args.limit <= 6
        and 1 <= args.max_calls <= 480
        and 1 <= args.deadline <= 2400
        and 1 <= args.variant_deadline <= 300
    ):
        raise SystemExit("Invalid evaluation bounds")
    directory = args.runtime.resolve() / "debug"
    if directory.parent.name != "runtime":
        raise SystemExit("Use ignored runtime only")
    if args.pilot and not args.pilot.resolve().is_relative_to(args.runtime.resolve()):
        raise SystemExit("Pilot must be inside the ignored runtime directory")
    directory.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(evaluate(args))
    path = directory / f"slice3-coverage-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, default=str)
    print(path)
    if result["budget"]["failure"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
