"""Opt-in bounded normal-pipeline development acceptance, never a medical gold test."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.core.debug_trace import trace_analysis
from app.core.diagnostics import diagnostic_secrets, sanitize_diagnostic
from app.db.session import SessionLocal
from app.models.analysis_run import AnalysisRunRecord
from app.orchestration.state import claim_runs, start_analysis
from app.orchestration.worker import build_orchestrator
from app.schemas.analysis import AnalysisInput, Consent, CreateAnalysisRequest
from app.validation.evaluation_budget import EvaluationBudget
from app.validation.replay import capture

CLAIMS = (
    "Smoking causes lung cancer.",
    "Frequent sunscreen use causes invasive melanoma.",
    "High blood pressure causes cancer.",
    "Eating carrots improves eyesight.",
)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Live acceptance is development/test only")
    claims = CLAIMS[:args.limit]
    if args.soy:
        claims += (
            "Regular soy consumption in men increases estrogen levels and lowers muscle gain.",
        )
    budget = EvaluationBudget(args.max_calls, args.deadline)
    output: dict[str, Any] = {
        "clinical_qualification": False, "configuration_changed": False,
        "origin": "new normal-pipeline development analyses", "analyses": [],
        "bounds": {"max_calls": args.max_calls, "deadline_seconds": args.deadline,
                   "analysis_timeout_seconds": 240, "claim_timeout_seconds": 180},
    }
    active_id: UUID | None = None
    try:
        with budget.measure():
            async with asyncio.timeout(args.deadline):
                for text in claims:
                    orchestrator = build_orchestrator(settings)
                    # Only tighten evaluation ceilings. Never extend deployed limits.
                    orchestrator.total_timeout_seconds = min(
                        240, orchestrator.total_timeout_seconds,
                    )
                    orchestrator.claim_timeout_seconds = min(
                        180, orchestrator.claim_timeout_seconds,
                    )
                    request = CreateAnalysisRequest(
                        client="api", lang="en", input=AnalysisInput(type="text", text=text),
                        consent=Consent(privacy_notice_version="2026-09-01", accepted=True),
                    )
                    with SessionLocal() as session:
                        row, _ = start_analysis(
                            session, request, idempotency_key=None,
                            retention_hours=settings.upload_retention_hours,
                        )
                        active_id = row.id
                        print(f"START {row.id} {text}", flush=True)
                        with trace_analysis(row.id, enabled=settings.debug_enabled):
                            await orchestrator.run(session, row.id, request)
                        exported = capture(session, row.id)
                        output["analyses"].append(exported)
                        session.refresh(row)
                        print(f"END {row.id} {row.status} {row.failure_code or ''}", flush=True)
                        active_id = None
    except TimeoutError:
        budget.failure = "evaluation_deadline_exceeded"
        # Only the new analysis reserved by this evaluator; never scan/replay
        # another worker's runs. Preserve append-only medical artifacts.
        if active_id is not None:
            with SessionLocal() as session:
                interrupted_row = session.get(AnalysisRunRecord, active_id)
                if interrupted_row is not None and interrupted_row.status in {"queued", "running"}:
                    interrupted_row.status = (
                        "partially_completed" if interrupted_row.completed_claims else "failed"
                    )
                    interrupted_row.failure_code = budget.failure
                    interrupted_row.finished_at = interrupted_row.updated_at = datetime.now(UTC)
                    for checkpoint in claim_runs(session, active_id):
                        if checkpoint.status in {"queued", "running"}:
                            checkpoint.status = "failed"
                            checkpoint.failure_code = budget.failure
                            checkpoint.finished_at = datetime.now(UTC)
                    session.commit()
                output["analyses"].append(capture(session, active_id))
    output["budget"] = budget.summary()
    return dict(sanitize_diagnostic(output, diagnostic_secrets(settings)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--limit", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--soy", action="store_true")
    parser.add_argument("--max-calls", type=int, default=400)
    parser.add_argument("--deadline", type=float, default=1100)
    parser.add_argument("--runtime", type=Path, default=Path("runtime"))
    args = parser.parse_args()
    if not args.run or not (1 <= args.max_calls <= 600 and 1 <= args.deadline <= 1200):
        raise SystemExit("Opt in with --run and bounded call/time limits")
    if args.runtime.resolve().name != "runtime":
        raise SystemExit("Use ignored runtime directory")
    output = asyncio.run(run(args))
    directory = args.runtime.resolve() / "debug"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"slice2-live-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2, default=str)
    print(path)
    if output["budget"]["failure"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
