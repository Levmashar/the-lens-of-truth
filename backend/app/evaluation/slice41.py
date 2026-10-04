"""Focused single-validator probes, never another judge/model bake-off."""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

from app.adapters.entailment import OpenAICompatibleEntailmentValidator
from app.core.config import Settings
from app.core.debug_trace import model_events, trace_analysis
from app.evaluation.artifacts import runtime_directory, save_artifact
from app.evaluation.slice41_cases import CASES, probe_judge
from app.judging.config import configured_slots
from app.validation.joint23 import finish_joint23, prepare_joint23
from app.validation.v2 import validate_v2


async def run(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    slot = next(s for s in configured_slots(settings) if s.slot == 3)
    validator = OpenAICompatibleEntailmentValidator(
        provider=slot.provider, model=slot.model, base_url=slot.base_url,
        api_key=slot.api_key, timeout_seconds=25,
    )
    rows = []
    expiry = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    cases = [c for c in CASES if not args.case or c.id in args.case]
    for case in cases[:args.limit]:
        judge, pack = probe_judge(case)
        prepared = prepare_joint23(judge, pack, "focused-probe")
        started = monotonic()
        row: dict[str, Any] = {"case": case.id, "origin": "synthetic engineering fixture",
                               "input_hash": prepared.prompt_hash, "input": prepared.user_prompt,
                               "model": slot.model, "expected_direction": case.direction,
                               "expected_scope": case.scope, "expected_strength": case.strength,
                               "expected_role": case.role}
        try:
            trace_id = uuid4()
            with trace_analysis(trace_id, enabled=True):
                async with asyncio.timeout(25):
                    response = await validator.assess_joint23(prepared)
            preflight = await validate_v2(judge, pack, None)
            audit = finish_joint23(preflight, judge, pack, response, prepared,
                                  risk_class="standard",
                                  provider=slot.provider, model=slot.model)
            row.update({"response": response.model_dump(mode="json"),
                        "qualified": audit.status == "validated",
                        "qualification": audit.result.conclusion_qualification,
                        "numeric_issues": [i.model_dump(mode="json")
                                           for i in audit.result.targeted_issues],
                        "failure": None})
        except Exception as exc:
            row["failure"] = type(exc).__name__
            row["failure_detail"] = str(exc)[:500]
            row["response_events"] = model_events(trace_id)
        row["latency_ms"] = round((monotonic() - started) * 1000)
        rows.append(row)
        save_artifact(runtime_directory(args.runtime), "slice41-probe-row",
                      {"purge_after": expiry, "row": row}, settings)
        print({"case": case.id, "failure": row["failure"],
               "assessment": (row.get("response") or {}).get("assessments"),
               "qualified": row.get("qualified")}, flush=True)
    return {"version": "slice41-focused-1.0", "purge_after": expiry, "rows": rows,
            "clinical_qualification": False, "annotations": "engineer-authored, not clinical gold"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--case", action="append")
    parser.add_argument("--limit", type=int, default=17)
    parser.add_argument("--runtime", type=Path, default=Path("../runtime"))
    args = parser.parse_args()
    settings = Settings(_env_file="../.env")  # type: ignore[call-arg]
    if not args.run or settings.app_env not in {"development", "test"} or not 1 <= args.limit <= 17:
        raise SystemExit("Opt in to at most 17 development/test focused probes")
    result = asyncio.run(run(args, settings))
    print(save_artifact(runtime_directory(args.runtime), "slice41-probes", result, settings))


if __name__ == "__main__":
    main()
