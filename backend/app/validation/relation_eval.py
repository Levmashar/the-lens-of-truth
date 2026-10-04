"""Opt-in, bounded paired semantic benchmark of configured validator aliases."""

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from time import monotonic
from typing import Any

import httpx

from app.adapters.entailment import OpenAICompatibleEntailmentValidator
from app.core.config import Settings
from app.core.diagnostics import diagnostic_secrets, sanitize_diagnostic
from app.judging.config import configured_slots, is_search_enabled_model
from app.validation.evaluation_budget import EvaluationBudget
from app.validation.relation_cases import CASES, HUMAN_REVIEWED, VERSION, RelationCase
from app.validation.relations import (
    PROMPT_VERSION,
    ClaimRelation,
    canonical_hash,
    prepare_relation_input,
)


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    good = [r for r in rows if r.get("response")]
    per_class = {}
    for label in ClaimRelation:
        expected = sum(r["expected_relation"] == label for r in rows)
        predicted = sum(r["response"]["relation"] == label for r in good)
        correct = sum(r["expected_relation"] == r["response"]["relation"] == label for r in good)
        per_class[label] = {
            "precision": correct / predicted if predicted else None,
            "recall": correct / expected if expected else None,
            "expected": expected,
            "predicted": predicted,
        }

    def false_decisive(label: ClaimRelation) -> dict[str, object]:
        denominator = sum(r["expected_relation"] != label for r in rows)
        failures = sum(
            r["expected_relation"] != label and r["response"]["relation"] == label for r in good
        )
        return {
            "count": failures,
            "denominator": denominator,
            "rate": failures / denominator if denominator else None,
        }

    decisive = [
        r
        for r in rows
        if r["expected_relation"] in {ClaimRelation.SUPPORTS, ClaimRelation.CONTRADICTS}
    ]
    over_abstain = sum(
        not r.get("response")
        or r["response"]["relation"]
        in {
            "insufficient",
            "context_only",
            "uncertain",
        }
        for r in decisive
    )
    return {
        "total_cases": total,
        "successful_responses": len(good),
        "relation_accuracy": sum(r["response"]["relation"] == r["expected_relation"] for r in good)
        / total
        if total
        else None,
        "scope_accuracy": sum(r["response"]["scope"] == r["expected_scope"] for r in good) / total
        if total
        else None,
        "materiality_accuracy": sum(
            r["response"]["materiality"] == r["expected_materiality"] for r in good
        )
        / total
        if total
        else None,
        "per_class": per_class,
        "false_support": false_decisive(ClaimRelation.SUPPORTS),
        "false_contradiction": false_decisive(ClaimRelation.CONTRADICTS),
        "false_rejection_over_abstention": {
            "count": over_abstain,
            "denominator": len(decisive),
            "rate": over_abstain / len(decisive) if decisive else None,
        },
        "schema_failure_rate": sum(r.get("failure") == "schema_failure" for r in rows) / total
        if total
        else None,
        "timeout_provider_failure_rate": sum(
            r.get("failure")
            in {
                "timeout",
                "provider_failure",
            }
            for r in rows
        )
        / total
        if total
        else None,
        "mean_latency_ms": mean(r["latency_ms"] for r in rows) if rows else None,
    }


async def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    setting_args: dict[str, Any] = {"_env_file": "../.env"}
    settings = Settings(**setting_args)
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Development/test evaluation only")
    slots = tuple(
        s
        for s in configured_slots(settings)
        if not is_search_enabled_model(s.model) and (not args.slot or s.slot in args.slot)
    )
    if not slots:
        raise SystemExit("No configured non-search semantic-capable slots")
    budget = EvaluationBudget(args.max_calls, args.deadline)
    output: dict[str, Any] = {
        "benchmark_version": VERSION,
        "relation_prompt_version": getattr(args, "prompt_version", PROMPT_VERSION),
        "human_reviewed": HUMAN_REVIEWED,
        "clinical_qualification": False,
        "origin": "engineer-authored synthetic conditional cases",
        "configuration_changed": False,
        "cases_sha256": canonical_hash(
            [
                {
                    "id": c.id,
                    "input": c.payload(),
                    "expected": c.expected,
                    "scope": c.scope,
                    "materiality": c.materiality,
                    "rationale": c.rationale,
                }
                for c in CASES
            ]
        ),
        "models": [],
    }
    selected = CASES[: args.limit]
    subset = tuple(
        c
        for c in selected
        if c.id
        in {
            "support-trial",
            "wide-null",
            "sunscreen-randomized",
            "reverse-carrot",
        }
    )[: args.stability]
    semaphore = asyncio.Semaphore(args.concurrency)

    async def one(
        case: RelationCase, validator: OpenAICompatibleEntailmentValidator, trial: int
    ) -> dict[str, Any]:
        prepared = prepare_relation_input(
            case.payload(),
            judge_run_id="benchmark",
            validation_run_id="benchmark",
            statement_ids=("S1",),
            prompt_version=getattr(args, "prompt_version", PROMPT_VERSION),
        )
        row: dict[str, Any] = {
            "case_id": case.id,
            "trial": trial,
            "expected_relation": case.expected,
            "expected_scope": case.scope,
            "expected_materiality": case.materiality,
            "prompt_hash": prepared.prompt_hash,
            "input": json.loads(prepared.user_prompt.split("\n", 1)[1]),
        }
        async with semaphore:
            started = monotonic()
            try:
                async with asyncio.timeout(20):
                    response = await validator.assess_relations(prepared)
                row["response"] = response.assessments[0].model_dump(mode="json")
            except (TimeoutError, httpx.TimeoutException):
                row["failure"] = "timeout"
            except (ValueError, TypeError, KeyError):
                row["failure"] = "schema_failure"
            except Exception:
                row["failure"] = "provider_failure"
            row["latency_ms"] = round((monotonic() - started) * 1000)
        return row

    try:
        with budget.measure():
            async with asyncio.timeout(args.deadline):
                for slot in slots:
                    model: dict[str, Any] = {
                        "slot": slot.slot,
                        "provider": slot.provider,
                        "model": slot.model,
                        "model_family": slot.model_family,
                        "identity_verified": False,
                        "baseline": [],
                        "stability_trials": [],
                    }
                    output["models"].append(model)
                    validator = OpenAICompatibleEntailmentValidator(
                        slot.provider,
                        slot.model,
                        slot.base_url,
                        slot.api_key,
                        timeout_seconds=18,
                    )
                    model["baseline"] = list(
                        await asyncio.gather(*(one(case, validator, 1) for case in selected))
                    )
                    model["metrics"] = metrics(model["baseline"])
                    print(
                        json.dumps(
                            {"slot": slot.slot, "model": slot.model, "metrics": model["metrics"]}
                        ),
                        flush=True,
                    )
                    model["stability_trials"] = list(
                        await asyncio.gather(
                            *(one(case, validator, trial) for case in subset for trial in (2, 3))
                        )
                    )
                    stability: list[dict[str, Any]] = []
                    for case in subset:
                        trials = [
                            r
                            for r in [*model["baseline"], *model["stability_trials"]]
                            if r["case_id"] == case.id
                        ]
                        responses = [r["response"] for r in trials if r.get("response")]
                        keys = {(r["relation"], r["scope"], r["materiality"]) for r in responses}
                        stability.append(
                            {
                                "case_id": case.id,
                                "trials": len(trials),
                                "successes": len(responses),
                                "identical_prompt": len({r["prompt_hash"] for r in trials}) == 1,
                                "relation_flip": len({r["relation"] for r in responses}) > 1,
                                "any_class_flip": len(keys) > 1,
                            }
                        )
                    model["stability"] = stability
                    completed = [s for s in stability if s["successes"] == 3]
                    model["stability_complete_cases"] = len(completed)
                    model["relation_flip_rate"] = (
                        sum(s["relation_flip"] for s in completed) / len(completed)
                        if completed
                        else None
                    )
                    model["any_class_flip_rate"] = (
                        sum(s["any_class_flip"] for s in completed) / len(completed)
                        if completed
                        else None
                    )
                    if budget.failure:
                        break
    except TimeoutError:
        budget.failure = "evaluation_deadline_exceeded"
    output["budget"] = budget.summary()
    output["composition"] = dict(Counter(c.category for c in selected))
    return dict(sanitize_diagnostic(output, diagnostic_secrets(settings)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--slot", type=int, choices=(1, 2, 3), action="append")
    parser.add_argument("--limit", type=int, default=len(CASES))
    parser.add_argument("--stability", type=int, default=4)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--max-calls", type=int, default=240)
    parser.add_argument("--deadline", type=float, default=360)
    parser.add_argument("--runtime", type=Path, default=Path("../runtime"))
    parser.add_argument("--prompt-version", choices=(PROMPT_VERSION,
                        "claim-relation-1.3-2026-10-01"), default=PROMPT_VERSION)
    args = parser.parse_args()
    if not args.run:
        raise SystemExit("Opt in with --run; this uses paid configured model calls")
    if not (
        1 <= args.limit <= len(CASES)
        and 0 <= args.stability <= 4
        and 1 <= args.concurrency <= 3
        and 1 <= args.max_calls <= 240
        and 1 <= args.deadline <= 600
    ):
        raise SystemExit("Invalid benchmark bounds")
    directory = args.runtime.resolve() / "debug"
    if directory.parent.name != "runtime":
        raise SystemExit("Use the ignored runtime directory")
    directory.mkdir(parents=True, exist_ok=True)
    output = asyncio.run(evaluate(args))
    path = directory / f"slice2-relations-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(path)
    if output["budget"]["failure"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
