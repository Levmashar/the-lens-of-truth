"""Opt-in frozen-input bake-off. No retrieval between models, tools or label leakage."""

import argparse
import asyncio
import json
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path
from statistics import median
from time import monotonic
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.adapters.entailment import OpenAICompatibleEntailmentValidator
from app.adapters.judge import OpenAICompatibleJudgeProvider, ProviderFailure
from app.adapters.model_catalog import discover_models
from app.core.config import Settings
from app.evaluation.artifacts import load_retained, runtime_directory, save_artifact
from app.evaluation.cases import BenchmarkCase, benchmark_cases
from app.evaluation.selection import lean_selection, oracle_selection
from app.judging.config import configured_slots, is_search_enabled_model
from app.judging.models import JudgeSlot
from app.judging.prompt import prepare_compact_v2, prepare_judge_input, prepare_minimal_v2
from app.judging.service import JudgeService
from app.judging.v3 import (
    DecisiveChecks,
    JudgeContentV3,
    derive_judge_position_v3,
    prepare_v3,
)
from app.retrieval.models import EvidencePack
from app.validation.evaluation_budget import EvaluationBudget, evaluation_row
from app.validation.joint import validate_joint
from app.validation.models import ValidationStatus
from app.validation.service import ValidationService


def row_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    def ratio(n: int, d: int) -> dict[str, Any]:
        return {"count": n, "denominator": d, "rate": n / d if d else None}
    negative_support = [r for r in rows if r.get("expected_position") not in {None, "supported"}]
    negative_against = [r for r in rows if r.get("expected_position") not in {None, "contradicted"}]
    semantic = [r for r in rows if r.get("expected_relation") is not None]
    annotated = [r for r in rows if r.get("expected_position") is not None]
    decisive_controls = [r for r in annotated if r["expected_position"] in
                         {"supported", "contradicted"}]
    attributions = [a for r in rows for a in (r.get("validation") or {}).get(
        "result", {}).get("statement_attributions", [])]
    latency = sorted(r["latency_ms"] for r in rows if r.get("latency_ms") is not None)
    return {
        "rows": total,
        "schema_success": ratio(sum(r.get("schema_valid", False) for r in rows), total),
        "usable": ratio(sum(r.get("position") is not None for r in rows), total),
        "position_agreement": ratio(sum(r.get("position") == r["expected_position"]
                                        and r.get("position") is not None for r in annotated),
                                    len(annotated)),
        "relation_agreement": ratio(sum(r.get("relation") == r["expected_relation"]
                                        for r in semantic), len(semantic)),
        "scope_agreement": ratio(sum(r.get("scope") == r["expected_scope"]
                                     for r in semantic), len(semantic)),
        "materiality_agreement": ratio(sum(r.get("materiality") == r["expected_materiality"]
                                           for r in semantic), len(semantic)),
        "false_support_position": ratio(sum(r.get("position") == "supported"
                                            for r in negative_support), len(negative_support)),
        "false_contradiction_position": ratio(sum(r.get("position") == "contradicted"
                                                for r in negative_against), len(negative_against)),
        "false_support_relation": ratio(sum(r.get("relation") == "supports_claim"
                                            for r in semantic
                                            if r["expected_relation"] != "supports_claim"),
                                        sum(r["expected_relation"] != "supports_claim"
                                            for r in semantic)),
        "false_contradiction_relation": ratio(sum(r.get("relation") == "contradicts_claim"
                                                  for r in semantic if
                                                  r["expected_relation"] != "contradicts_claim"),
                                              sum(r["expected_relation"] != "contradicts_claim"
                                                  for r in semantic)),
        "decisive": ratio(sum(r.get("position") in {"supported", "contradicted"}
                              for r in rows), total),
        "nei": ratio(sum(r.get("position") == "not_enough_evidence" for r in rows), total),
        "unable": ratio(sum(r.get("position") is None for r in rows), total),
        "provisional_decisive_rejection": ratio(sum(r.get("position") != r["expected_position"]
                                                    for r in decisive_controls),
                                                len(decisive_controls)),
        "statement_attribution_success": ratio(sum(a["status"] == "supported_by_sources"
                                                   for a in attributions), len(attributions)),
        "input_tokens": sum(r.get("input_tokens", 0) or 0 for r in rows),
        "output_tokens": sum(r.get("output_tokens", 0) or 0 for r in rows),
        "p50_latency_ms": median(latency) if latency else None,
        "p95_latency_ms": latency[ceil(len(latency) * .95) - 1] if latency else None,
        "failures": dict(Counter(r.get("failure") for r in rows if r.get("failure"))),
        "numeric_issues": sum(r.get("numeric_issues", 0) for r in rows),
        "calls": sum(r.get("calls", 0) for r in rows),
    }


def expected_position(case: BenchmarkCase) -> str:
    # Annotation-derived policy oracle, not a medical label. A V3-shaped
    # stipulated assessment is run through exactly the same design/numeric gate.
    annotation = case.annotation
    doc = case.pack.documents[0]
    basis = ("randomized_intervention" if doc.relationship_analysis and
             doc.relationship_analysis.exposure_assignment == "randomized" else
             "evidence_synthesis" if doc.study_design in {"systematic_review", "meta_analysis"}
             else "observational_association")
    content = JudgeContentV3.model_validate_json(json.dumps({
        "assessments": [{"assessment_id": "A1", "source_id": doc.document_id,
                         "evidence_unit_ids": ["E1.U1"], "relation": annotation.expected,
                         "scope": annotation.scope, "materiality": annotation.materiality,
                         "evidence_basis": basis, "reason_codes": ["DIRECT_FINDING"]}],
        "overall_uncertainty_reasons": [],
    }))
    result = derive_judge_position_v3(content, prepare_v3(prepare_judge_input(uuid4(), case.pack)),
                                      case.pack)
    return str(result.position or "unable_to_verify_reliably")


async def one(
    pack: EvidencePack, slot: JudgeSlot, validator_slot: JudgeSlot, architecture: str,
    budget: EvaluationBudget,
) -> dict[str, Any]:
    start = monotonic()
    row_id = str(uuid4())
    base = prepare_judge_input(uuid5(NAMESPACE_URL, pack.snapshot_hash), pack)
    if architecture == "v2-minimal":
        base = prepare_minimal_v2(base)
    if architecture == "v2-joint":
        base = prepare_compact_v2(base)
    prepared = prepare_v3(base) if architecture.startswith("v3") else base
    token = evaluation_row.set(row_id)
    row: dict[str, Any] = {"model": slot.model, "family": slot.model_family,
                          "architecture": architecture, "pack_hash": pack.snapshot_hash,
                          "input_hash": prepared.input_snapshot_hash,
                          "prompt_hash": prepared.prompt_hash,
                          "generation": {"temperature": 0, "top_p": None, "seed": None},
                          "schema_valid": False, "position": None, "failure": None}
    provider = OpenAICompatibleJudgeProvider(45)
    try:
        async with asyncio.timeout(90):
            if architecture.startswith("v2"):
                service = JudgeService(providers={slot.provider: provider},
                                       attempt_timeout_seconds=45, total_timeout_seconds=80)
                run = await service._run_slot(pack, base, slot)
                row["judge_run"] = run.model_dump(mode="json")
                row["schema_valid"] = run.decision is not None
                if run.decision is None:
                    row["failure"] = run.error_category
                else:
                    validator = OpenAICompatibleEntailmentValidator(
                        provider=validator_slot.provider, model=validator_slot.model,
                        base_url=validator_slot.base_url, api_key=validator_slot.api_key,
                    )
                    audit = (await validate_joint(run, pack, validator)
                             if architecture == "v2-joint" else
                             await ValidationService(semantic_validator=validator).run(run, pack))
                    row["validation"] = audit.model_dump(mode="json")
                    row["numeric_issues"] = sum(i.issue_code == "NUMERIC_UNCERTAIN" for i in
                                                audit.result.targeted_issues)
                    if audit.status == ValidationStatus.VALIDATED:
                        row["position"] = run.decision.label
                    else:
                        row["failure"] = f"validation_{audit.status}"
                    relations = cast(
                        list[dict[str, Any]],
                        (audit.result.relation_validation or {}).get("assessments", []),
                    )
                    if relations:
                        row.update({k: relations[0][k]
                                    for k in ("relation", "scope", "materiality")})
            else:
                response = None
                for attempt in range(2):
                    try:
                        response = await provider.evaluate(slot, prepared)
                        if len(response.content) > 32768:
                            raise ValueError("Oversized structured response")
                        content = JudgeContentV3.model_validate_json(response.content)
                        break
                    except ProviderFailure as exc:
                        if attempt or not exc.retryable:
                            raise
                        if exc.category == "response_format_unsupported":
                            slot = slot.model_copy(update={"request_json_schema": False})
                    except ValueError:
                        if attempt:
                            raise
                assert response is not None
                row.update({"schema_valid": True, "response": content.model_dump(mode="json"),
                            "returned_model": response.model_snapshot,
                            "system_fingerprint": response.system_fingerprint,
                            "response_id": response.response_id,
                            "request_id": response.provider_request_id,
                            "input_tokens": response.input_tokens,
                            "output_tokens": response.output_tokens})
                check = None
                hardened = architecture in {"v3-hardened", "v3-hardened-crosscheck"}
                preliminary = derive_judge_position_v3(content, prepared, pack, hardened=hardened)
                if (architecture in {"v3-crosscheck", "v3-hardened-crosscheck"}
                        and preliminary.position in {"supported", "contradicted"}):
                    check = await crosscheck(content, prepared, validator_slot)
                    row["crosscheck"] = check
                derived = derive_judge_position_v3(content, prepared, pack, crosscheck=check,
                                                   hardened=hardened)
                row["derived"] = derived.model_dump(mode="json")
                row["position"] = derived.position
                row["failure"] = derived.operational_failure
                first = content.assessments[0]
                row.update({k: getattr(first, k) for k in ("relation", "scope", "materiality")})
    except TimeoutError:
        row["failure"] = "timeout"
    except ProviderFailure as exc:
        row["failure"] = exc.category
    except (ValueError, KeyError, TypeError) as exc:
        row["failure"] = f"schema_or_reference_{type(exc).__name__}"
    row["latency_ms"] = round((monotonic() - start) * 1000)
    measured = [c for c in budget.calls if c.get("evaluation_row") == row_id]
    row["calls"] = len(measured)
    row["input_tokens"] = sum(c.get("usage", {}).get("prompt_tokens", 0) or 0 for c in measured)
    row["output_tokens"] = sum(c.get("usage", {}).get("completion_tokens", 0) or 0
                               for c in measured)
    row["http_statuses"] = dict(Counter(str(c.get("http_status")) for c in measured))
    row["response_success"] = any(c.get("http_status") == 200 for c in measured)
    judge_call = next((c for c in measured if c.get("model") == slot.model and
                       c.get("http_status") == 200), {})
    for key in ("returned_model", "system_fingerprint", "response_id", "provider_request_id"):
        if key in judge_call:
            row[key] = judge_call[key]
    evaluation_row.reset(token)
    return row


async def crosscheck(content: JudgeContentV3, prepared: Any, slot: JudgeSlot) -> dict[str, str]:
    """One batched, non-voting decisive-use review, no new relations or verdict."""
    decisive = [a.model_dump(mode="json") for a in content.assessments
                if a.materiality == "decisive"]
    if not decisive:
        return {}
    ids = {identifier for a in decisive for identifier in a["evidence_unit_ids"]}
    payload = {"claim": prepared.input_snapshot_json["claim"], "assessments": decisive,
               "units": [u for u in prepared.input_snapshot_json["source_units"]
                         if u["unit_id"] in ids],
               "document_bundles": prepared.input_snapshot_json["document_bundles"]}
    instructions = (
        "Review each proposed decisive evidence classification using ONLY frozen units. "
        "No tools, browsing, outside facts, verdict or new relation. Return JSON "
        '{"checks":[{"assessment_id":"A1","status":"valid|invalid|uncertain"}]}. '
        "Invalid if causality/scope/magnitude is overstated, null interpreted as no effect, "
        "wrong comparator/endpoint/population, or context promoted to decisive. Exact IDs."
    )
    probe = replace(prepared, system_prompt=instructions,
                    user_prompt=json.dumps(payload, sort_keys=True),
                    input_snapshot_version="crosscheck-development")
    # Prompt-only JSON with strict local status/id validation; no unsupported
    # reuse of judge schema, no retry, one request maximum.
    response = await OpenAICompatibleJudgeProvider(45).evaluate(
        slot.model_copy(update={"request_json_schema": False}), probe)
    data = DecisiveChecks.model_validate_json(response.content)
    checks = data.checks
    result: dict[str, str] = {item.assessment_id: item.status for item in checks}
    if len(result) != len(checks) or set(result) != {a["assessment_id"] for a in decisive}:
        raise ValueError("Crosscheck ID mismatch")
    if any(s not in {"valid", "invalid", "uncertain"} for s in result.values()):
        raise ValueError("Crosscheck status mismatch")
    return result


async def evaluate(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    slots = configured_slots(settings)
    if not slots or settings.app_env not in {"development", "test"}:
        raise ValueError("Configured development/test gateway required")
    catalog = await discover_models(slots[0])
    eligible = {r["model"] for r in catalog if r["eligible"]}
    candidates = args.model or [s.model for s in slots]
    if not 1 <= len(set(candidates)) <= 8 or any(m not in eligible for m in candidates):
        raise ValueError("Use at most eight real, non-search catalog chat models")
    budget = EvaluationBudget(args.max_calls, args.deadline)
    rows: list[dict[str, Any]] = []
    cases: list[tuple[str, EvidencePack, BenchmarkCase | None]] = []
    origins: dict[str, str] = {}
    expiries = [datetime.now(UTC) + timedelta(hours=1)]
    if args.capture:
        for path in args.capture:
            artifact = load_retained(path)
            expiries.append(datetime.fromisoformat(artifact["purge_after"]))
            for claim in artifact["claims"]:
                if claim.get("pack"):
                    pack = EvidencePack.model_validate(claim["pack"]["snapshot_json"])
                    cases.append((str(pack.claim_id), pack, None))
                    origins[str(pack.claim_id)] = claim.get("origin") or artifact.get(
                        "origin") or artifact.get("availability") or "frozen_capture_unclassified"
    else:
        for c in benchmark_cases():
            if ((not args.case or c.id in args.case) and
                    (args.split == "all" or c.split == args.split)):
                cases.append((c.id, c.pack, c))
        cases = cases[:args.limit]
    semaphore = asyncio.Semaphore(args.concurrency)
    oracle = json.loads(args.oracle.read_text(encoding="utf-8")) if args.oracle else {}
    cases = [(i, p, c) for i, p, c in cases if
             (not args.case or i in args.case) and (not args.oracle or i in oracle)][:args.limit]
    progress = runtime_directory(args.runtime) / (
        f"progress-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.jsonl")
    # Exclusive file creation, then append-only checkpoints. An evaluator crash
    # must not discard paid responses already received. Same original retention.
    with progress.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps({"purge_after": min(expiries).isoformat(),
                                 "models": candidates}) + "\n")

    async def job(case_id: str, pack: EvidencePack, case: BenchmarkCase | None,
                  architecture: str, model: str, repeat: int, selection: str) -> None:
        async with semaphore:
            if budget.failure:
                return
            chosen = (lean_selection(pack) if selection == "lean" else
                      oracle_selection(pack, tuple(oracle[case_id])) if selection == "oracle"
                      else pack)
            template = next((s for s in slots if s.model == model), slots[0])
            slot = template.model_copy(update={"model": model,
                                               "model_family": model.split("/")[0]})
            validator_slot = next((s for s in reversed(slots)
                                   if s.model != model and not is_search_enabled_model(s.model)),
                                  slots[-1])
            if args.validator:
                if args.validator not in eligible:
                    raise ValueError("Validator must be in catalog")
                validator_slot = slots[0].model_copy(update={
                    "model": args.validator, "model_family": args.validator.split("/")[0],
                })
            try:
                row = await one(chosen, slot, validator_slot, architecture, budget)
            except ValueError:
                # A Pack rejected by existing visibility/provenance rules is
                # an operational exclusion. Do not weaken those rules for oracle.
                row = {"model": model, "architecture": architecture, "schema_valid": False,
                       "position": None, "failure": "preparation_policy_blocked", "calls": 0}
            row.update({"case_id": case_id, "repeat": repeat, "selection": selection,
                        "split": case.split if case else "real_frozen",
                        "origin": case.origin if case else origins[case_id],
                        "validator": {"provider": validator_slot.provider,
                                      "model": validator_slot.model,
                                      "claimed_family": validator_slot.model_family},
                        "claim": pack.claim_snapshot.standalone_text})
            if case:
                row.update({"expected_relation": case.annotation.expected,
                            "expected_scope": case.annotation.scope,
                            "expected_materiality": case.annotation.materiality,
                            "expected_position": expected_position(case)})
            rows.append(row)
            from app.core.diagnostics import diagnostic_secrets, sanitize_diagnostic
            with progress.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(sanitize_diagnostic(row, diagnostic_secrets(settings)),
                                        ensure_ascii=False, default=str) + "\n")
            print(json.dumps({k: row.get(k) for k in (
                "case_id", "model", "architecture", "repeat", "selection", "schema_valid",
                "position", "failure", "calls", "latency_ms")}), flush=True)

    try:
        with budget.measure():
            async with asyncio.timeout(args.deadline):
                await asyncio.gather(*(job(case_id, pack, case, architecture,
                                          model, repeat, variant)
                    for case_id, pack, case in cases for architecture in args.architecture
                    for model in candidates for repeat in range(args.repeats)
                    for variant in args.selection))
    except TimeoutError:
        budget.failure = "evaluation_deadline_exceeded"
    except ValueError:
        if not budget.failure:
            raise
    return {"version": "judge-bakeoff-1.0", "clinical_qualification": False,
            "human_reviewed": False, "identity_verified": False, "models": candidates,
            "planned_rows": len(cases) * len(args.architecture) * len(candidates)
                            * args.repeats * len(args.selection),
            "purge_after": min(expiries).isoformat(),
            "rows": rows, "budget": budget.summary(), "metrics": {
                f"{m}:{a}": row_metrics([r for r in rows if r["model"] == m and
                                         r["architecture"] == a])
                for m in candidates for a in args.architecture}, "cost_usd": None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--model", action="append")
    parser.add_argument("--validator")
    parser.add_argument("--architecture", action="append",
                        choices=("v2", "v2-minimal", "v2-joint", "v3", "v3-crosscheck",
                                 "v3-hardened", "v3-hardened-crosscheck"))
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--split", choices=("all", "development", "held_out"), default="all")
    parser.add_argument("--case", action="append")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--capture", type=Path, action="append")
    parser.add_argument("--selection", choices=("current", "lean", "oracle"), action="append")
    parser.add_argument("--oracle", type=Path)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--max-calls", type=int, default=240)
    parser.add_argument("--deadline", type=float, default=900)
    parser.add_argument("--runtime", type=Path, default=Path("../runtime"))
    args = parser.parse_args()
    if not args.run:
        raise SystemExit("Opt in with --run; paid calls, private ignored runtime artifacts")
    if not (1 <= args.limit <= 40 and 1 <= args.repeats <= 5 and
            1 <= args.max_calls <= 1200 and 1 <= args.deadline <= 3600 and
            1 <= args.concurrency <= 6):
        raise SystemExit("Invalid evaluation bounds")
    args.architecture = args.architecture or ["v2"]
    args.selection = args.selection or ["current"]
    settings = Settings(_env_file="../.env")  # type: ignore[call-arg]
    result = asyncio.run(evaluate(args, settings))
    print(save_artifact(runtime_directory(args.runtime), "bakeoff", result, settings))
    print(json.dumps(result["metrics"]))
    if result["budget"]["failure"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
