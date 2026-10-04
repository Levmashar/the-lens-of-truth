"""Opt-in acceptance via the exact frontend HTTP contract, with normal configuration."""

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.evaluation.artifacts import runtime_directory, save_artifact
from app.evaluation.source_suite import CONTROLS

TEXTS = tuple(CONTROLS[i][0] for i in (0, 1, 2, 3, 4, 5, 7, 8)) + (
    "Regular soy consumption in men increases estrogen levels and lowers muscle gain.",
)


async def run(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    if settings.app_env not in {"development", "test"}:
        raise ValueError("Development/test only")
    rows = []
    calls: set[str] = set()
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=20) as client:
        health = await client.get("/healthz")
        health.raise_for_status()
        texts = args.text or TEXTS[args.offset:args.offset + args.limit]
        for text in texts:
            if len(calls) >= args.max_observed_calls:
                break
            start = monotonic()
            response = await client.post("/v1/analyses", headers={"Idempotency-Key": str(uuid4())},
                json={"schema_version": "1.0", "client": "web", "lang": "auto",
                      "input": {"type": "text", "text": text}, "consent": {
                          "privacy_notice_version": "2026-09-01", "accepted": True}})
            response.raise_for_status()
            identifier = response.json()["analysis_id"]
            progress: dict[str, Any] = {}
            while monotonic() - start < args.analysis_deadline:
                response = await client.get(f"/v1/analyses/{identifier}")
                response.raise_for_status()
                progress = response.json()
                if progress["status"] in {"completed", "failed", "partially_completed"}:
                    break
                await asyncio.sleep(2)
            observed = {e["call_id"] for e in progress.get("debug_events") or []
                        if e.get("call_id") and e["status"] != "calling"}
            calls.update(observed)
            summaries = await client.get(f"/v1/analyses/{identifier}/claims")
            summaries.raise_for_status()
            summary = summaries.json()
            reports = []
            for claim in summary["claims"]:
                if claim.get("report_run_id"):
                    report = await client.get(
                        f"/v1/analyses/{identifier}/claims/{claim['claim_id']}/report")
                    report.raise_for_status()
                    reports.append(report.json())
            row = {"input": text, "analysis_id": identifier, "progress": progress,
                   "summaries": summary, "reports": reports,
                   "observed_model_calls": len(observed),
                   "latency_ms": round((monotonic() - start) * 1000)}
            rows.append(row)
            checkpoint = {"purge_after": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                          "row": row}
            save_artifact(runtime_directory(args.runtime), "acceptance-row", checkpoint, settings)
            print(json.dumps({"analysis_id": identifier, "status": progress["status"],
                              "claims": [(c["status"], c.get("result_label"))
                                         for c in summary["claims"]],
                              "calls": len(observed), "latency_ms": row["latency_ms"]}), flush=True)
    return {"version": "normal-http-acceptance-1.0", "clinical_qualification": False,
            "configuration_changed": False, "models_replaced": False,
            "purge_after": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "rows": rows, "observed_model_calls": len(calls),
            "call_budget_note": "Admission cap only; an admitted normal analysis finishes normally"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--limit", type=int, default=9)
    parser.add_argument("--offset", type=int, default=0,
                        help="Skip completed controls without replaying paid analyses")
    parser.add_argument("--text", action="append", help="Explicit bounded acceptance inputs")
    parser.add_argument("--analysis-deadline", type=float, default=300)
    parser.add_argument("--max-observed-calls", type=int, default=120)
    parser.add_argument("--runtime", type=Path, default=Path("../runtime"))
    args = parser.parse_args()
    if args.text and (len(args.text) > 9 or any(not t.strip() or len(t) > 2000 for t in args.text)):
        raise SystemExit("Use at most nine explicit inputs, each 1-2000 characters")
    if not args.run or not (0 <= args.offset <= 8 and 1 <= args.limit <= 9 and
                            args.offset + args.limit <= 9 and
                            1 <= args.analysis_deadline <= 360 and
                            1 <= args.max_observed_calls <= 150):
        raise SystemExit("Opt in with --run and bounded limits")
    settings = Settings(_env_file="../.env")  # type: ignore[call-arg]
    result = asyncio.run(run(args, settings))
    print(save_artifact(runtime_directory(args.runtime), "acceptance", result, settings))


if __name__ == "__main__":
    main()
