"""Opt-in bounded Slice 1 evaluation; no retrieval or historical artifact writes.

Expectations are engineer-authored attribution tests, not reviewed clinical
conclusions. Retained captures are used only until their original expiry.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx

from app.adapters.entailment import OpenAICompatibleEntailmentValidator
from app.adapters.judge import OpenAICompatibleJudgeProvider
from app.core.config import Settings
from app.core.diagnostics import diagnostic_secrets, sanitize_diagnostic
from app.judging.config import configured_slots
from app.judging.service import JudgeService
from app.retrieval.models import EvidencePack
from app.validation.assertion_numeric import compare_assertion_numbers
from app.validation.models import NumericAlignment, StatementAttributionStatus, ValidationStatus
from app.validation.semantic import prepare_semantic_input
from app.validation.v2 import validate_v2

# Five correct and five incorrect/unsupported statements. These are synthetic
# attribution controls, not reconstructions of an expired original analysis.
CONTROLS = (
    ("qualitative-ci", "The study did not establish a statistically significant effect.",
     "RR 0.85 (95% CI 0.70-1.04) was not statistically significant.", True),
    ("correct-risk-conversion", "The trial reported a 15% risk reduction.", "RR 0.85.", True),
    ("bad-risk-conversion", "The trial reported an 85% risk reduction.", "RR 0.85.", False),
    ("ratio-substitution", "The study reported OR 0.85.", "RR 0.85.", False),
    ("wrong-study", "Study A reported RR 0.80.", "Study B reported RR 0.15.", False),
    ("accurate-user-contrast", "The trial observed a 15% reduction, below the claimed 80%.",
     "The trial observed a 15% reduction; its narrow interval excluded an 80% reduction.", True),
    ("missing-dose", "The study established that 80 mg is an effective dose.",
     "The dose was not reported; efficacy could not be assessed.", False),
    ("wrong-ci-binding", "The trial reported HR 0.27 (95% CI 0.29-1.81).",
     "Invasive: HR 0.27 (95% CI 0.08-0.97). Preinvasive: HR 0.73 (95% CI 0.29-1.81).", False),
    ("comma-ci", "The trial reported HR 0.27 (95% CI 0.08-0.97).",
     "The invasive endpoint had HR, 0.27; 95% CI, 0.08 to 0.97.", True),
    ("literal-negation", "The study reported no association between X and Y.",
     "The study reported no association between X and Y.", True),
)


async def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    settings_args: dict[str, Any] = {"_env_file": Path("../.env")}
    settings = Settings(**settings_args)
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Slice 1 evaluation is development/test only.")
    slots = configured_slots(settings)
    judge_slot = next(s for s in slots if s.slot == args.judge_slot)
    validator_slot = next(s for s in slots if s.slot == args.validator_slot)
    if judge_slot.model_family == validator_slot.model_family:
        raise SystemExit("Use a different configured validator family for the frozen judge probes.")
    output: dict[str, Any] = {
        "contract": "slice1-evaluation-1.0", "clinical_validation": False,
        "expectation_origin": "engineer-authored synthetic attribution controls",
        "configuration": [{"slot": s.slot, "provider": s.provider, "model": s.model,
                           "model_family": s.model_family} for s in (judge_slot, validator_slot)],
        "controls": [], "frozen_runs": [], "http_calls": 0,
        "call_diagnostics": [],
        "input_tokens": 0, "output_tokens": 0,
    }
    started = monotonic()
    deadline_at = started + args.deadline

    async def before_request(request: httpx.Request) -> None:
        if monotonic() >= deadline_at:
            output["evaluation_failure"] = "total_deadline_exceeded"
            raise TimeoutError("evaluation_deadline_exceeded")
        if output["http_calls"] >= args.max_calls:
            output["evaluation_failure"] = "call_budget_exhausted"
            raise ValueError("evaluation_call_budget_exhausted")
        output["http_calls"] += 1
        payload = json.loads(request.content)
        index = len(output["call_diagnostics"])
        request.extensions["slice1_call_index"] = index
        request.extensions["slice1_call_started"] = monotonic()
        # Developer-only exact inputs and visible outputs; never headers,
        # URLs, keys, provider reasoning, or transport internals.
        output["call_diagnostics"].append({
            "call_number": output["http_calls"], "model": payload.get("model"),
            "messages": payload.get("messages"),
            "native_schema_requested": "response_format" in payload,
            "http_status": None,
        })

    async def after_response(response: httpx.Response) -> None:
        await response.aread()
        diagnostic = output["call_diagnostics"][response.request.extensions["slice1_call_index"]]
        diagnostic["http_status"] = response.status_code
        diagnostic["elapsed_ms"] = round((monotonic() - response.request.extensions[
            "slice1_call_started"]) * 1000)
        try:
            body = response.json()
            usage = body.get("usage") or {}
            diagnostic["usage"] = usage
            choices = body.get("choices") or []
            if choices:
                content = choices[0].get("message", {}).get("content")
                if isinstance(content, str):
                    diagnostic["visible_response"] = content[:32768]
                    diagnostic["response_truncated"] = len(content) > 32768
            output["input_tokens"] += usage.get("prompt_tokens", 0) or 0
            output["output_tokens"] += usage.get("completion_tokens", 0) or 0
        except (ValueError, TypeError, AttributeError):
            pass

    class MeasuredClient(httpx.AsyncClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs, event_hooks={"request": [before_request],
                                                   "response": [after_response]})

    # Instrument only this opt-in process, including native-schema fallback calls.
    client_patch = patch("httpx.AsyncClient", MeasuredClient)
    client_patch.start()
    validator = OpenAICompatibleEntailmentValidator(
        provider=validator_slot.provider, model=validator_slot.model,
        base_url=validator_slot.base_url, api_key=validator_slot.api_key, timeout_seconds=18,
    )
    try:
        async with asyncio.timeout(args.deadline):
            for name, statement, source, expected in CONTROLS[:args.controls_limit]:
                numeric = compare_assertion_numbers(statement, (source,),
                                                     user_claim="X reduces Y by 80%."
                                                     if name == "accurate-user-contrast" else None)
                prepared = prepare_semantic_input(
                    "statement_attribution", {
                        "statement": {"statement_id": "S1", "text": statement,
                                      "kind": "study_finding", "source_unit_ids": ["E1.U1"]},
                        "frozen_passages": [{"evidence_id": "E1", "section": "RESULTS",
                                             "passage": source, "title": "Synthetic fixture",
                                             "pmid": "synthetic", "study_design": "unknown",
                                             "integrity": "valid"}],
                        "numeric_verification": numeric.diagnostic(),
                    }, judge_run_id=str(uuid4()), validation_run_id=str(uuid4()),
                    statement_ids=("S1",), evidence_ids=("E1",),
                )
                case: dict[str, Any] = {"name": name, "expected_attribution_accepted": expected,
                                        "statement": statement, "source": source,
                                        "numeric": numeric.diagnostic(),
                                        "transport_schema_success": False}
                output["controls"].append(case)
                try:
                    response = await validator.assess_statement(prepared)
                    case["transport_schema_success"] = True
                    case["semantic_response"] = response.model_dump(mode="json")
                    case["semantic_accepted"] = (
                        response.status == StatementAttributionStatus.SUPPORTED_BY_SOURCES)
                    case["combined_accepted"] = (case["semantic_accepted"] and numeric.status in {
                        NumericAlignment.ALIGNED, NumericAlignment.NOT_APPLICABLE})
                except Exception as exc:
                    case["provider_or_format_failure"] = type(exc).__name__
                print(f"{name}: expected={expected} numeric={numeric.status.value} "
                      f"semantic={case.get('semantic_accepted', 'unavailable')}", flush=True)
            for path in args.capture:
                capture = json.loads(Path(path).read_text(encoding="utf-8"))
                if capture.get("availability") != "retained_original":
                    output["frozen_runs"].append({"capture": str(path), "status": "not_retained"})
                    continue
                if datetime.fromisoformat(capture["purge_after"]) <= datetime.now(UTC):
                    output["frozen_runs"].append({"capture": str(path),
                                                 "status": "expired_skipped"})
                    continue
                for claim in capture["claims"]:
                    pack_record = claim["pack"]
                    pack = EvidencePack.model_validate(pack_record["snapshot_json"])
                    service = JudgeService(
                        {judge_slot.provider: OpenAICompatibleJudgeProvider(45)},
                        attempt_timeout_seconds=45, total_timeout_seconds=80,
                    )
                    record: dict[str, Any] = {"analysis_id": capture["analysis_id"],
                                             "purge_after": capture["purge_after"],
                                             "original_artifact": True,
                                             "new_evaluation_invocation": True,
                                             "state": "judge_in_progress"}
                    output["frozen_runs"].append(record)
                    runs, _ = await service.run(
                        UUID(pack_record["id"]), pack, (judge_slot,), app_env=settings.app_env,
                        allow_search_enabled_development=settings.judge_allow_search_enabled_development,
                    )
                    run = runs[0]
                    record["judge"] = run.model_dump(mode="json")
                    record["state"] = "validating" if run.decision else "judge_failed"
                    if run.decision:
                        audit = await validate_v2(run, pack, validator)
                        record["validation"] = audit.model_dump(mode="json")
                        record["conclusion_eligible"] = audit.status == ValidationStatus.VALIDATED
                        if (getattr(args, "revise", False) and audit.result.targeted_issues
                                and (audit.status in {ValidationStatus.INVALID,
                                                     ValidationStatus.PARTIALLY_VALIDATED}
                                     or any(i.issue_code.value == "NUMERIC_UNCERTAIN"
                                            for i in audit.result.targeted_issues))):
                            record["state"] = "revision_in_progress"
                            child = await service.revise(run, audit, pack, judge_slot)
                            record["revision"] = {"judge": child.model_dump(mode="json")}
                            record["active_judge_run_id"] = str(child.judge_run_id)
                            record["conclusion_eligible"] = False
                            if child.decision:
                                child_audit = await validate_v2(child, pack, validator)
                                record["revision"]["validation"] = child_audit.model_dump(
                                    mode="json")
                                record["conclusion_eligible"] = (
                                    child_audit.status == ValidationStatus.VALIDATED)
                    record["state"] = "completed" if run.decision else "judge_failed"
                    print(f"{capture['analysis_id']}: judge={run.outcome_status} "
                          f"conclusion_eligible={record.get('conclusion_eligible', False)}",
                          flush=True)
    except TimeoutError:
        output["evaluation_failure"] = "total_deadline_exceeded"
    finally:
        client_patch.stop()
    output["elapsed_seconds"] = round(monotonic() - started, 3)
    expiries = [r["purge_after"] for r in output["frozen_runs"] if r.get("purge_after")]
    if expiries:
        output["purge_after"] = min(expiries)
    completed = [c for c in output["controls"] if c["transport_schema_success"]]
    output["metrics"] = {
        "cases_planned": args.controls_limit, "cases_completed": len(completed),
        "positive_controls": sum(c["expected_attribution_accepted"] for c in completed),
        "negative_controls": sum(not c["expected_attribution_accepted"] for c in completed),
        "semantic_false_rejections": sum(c["expected_attribution_accepted"] and
                                         not c["semantic_accepted"] for c in completed),
        "semantic_false_acceptances": sum(not c["expected_attribution_accepted"] and
                                          c["semantic_accepted"] for c in completed),
        "combined_false_rejections": sum(c["expected_attribution_accepted"] and
                                         not c["combined_accepted"] for c in completed),
        "combined_false_acceptances": sum(not c["expected_attribution_accepted"] and
                                          c["combined_accepted"] for c in completed),
        "provider_format_failures": sum(not c["transport_schema_success"]
                                        for c in output["controls"]),
    }
    return dict(sanitize_diagnostic(output, diagnostic_secrets(settings)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--capture", action="append", default=[])
    parser.add_argument("--revise", action="store_true",
                        help="Exercise the existing one-child same-evidence revision budget")
    parser.add_argument("--controls-limit", type=int, choices=range(0, 11), default=10)
    parser.add_argument("--judge-slot", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--validator-slot", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--max-calls", type=int, choices=range(1, 31), default=24)
    parser.add_argument("--deadline", type=int, choices=range(30, 361), default=300)
    args = parser.parse_args()
    result = asyncio.run(evaluate(args))
    output = Path(__file__).resolve().parents[3] / "runtime" / "reliability"
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"slice1-eval-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result["metrics"]))
    print(f"calls={result['http_calls']} elapsed={result['elapsed_seconds']}s -> {path}")
    print("Engineer-authored attribution evaluation; no clinical or production qualification.")
    if result.get("evaluation_failure") or result["metrics"]["provider_format_failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
