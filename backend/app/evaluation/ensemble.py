"""Offline subset comparison through the unchanged, provenance-checking Lens policy.

Only V2 audit artifacts are compatible. V3 positions are not fabricated into
approved judge/validation records. Engineering controls are not clinical gold.
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.core.config import Settings
from app.evaluation.artifacts import load_retained, runtime_directory, save_artifact
from app.evaluation.cases import benchmark_cases
from app.judging.models import JudgeRun
from app.validation.models import JudgeValidationRun
from app.verdict.models import AggregationContext, AggregationInput, AggregationMode, ClaimFacts
from app.verdict.policy import POLICY_V4
from app.verdict.service import VerdictService

LITE = "google/gemini-2.5-flash-lite"
LUNA = "openai/gpt-6-luna"
LING = "inclusionai/ling-3.0-flash"
SUBSETS = {"single_lite": (LITE,), "two_lite_luna": (LITE, LUNA),
           "three_current": (LITE, LUNA, LING)}


def compare(artifact: dict[str, Any]) -> dict[str, Any]:
    cases = {case.id: case for case in benchmark_cases()}
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for row in artifact["rows"]:
        if row["architecture"].startswith("v2") and row["case_id"] in cases:
            if row.get("selection", "current") != "current":
                continue
            groups.setdefault((row["case_id"], row["architecture"], row["repeat"]), []).append(row)
    results: list[dict[str, Any]] = []
    for (identifier, architecture, repeat), group in groups.items():
        case = cases[identifier]
        pack = case.pack
        pack_id = uuid5(NAMESPACE_URL, pack.snapshot_hash)
        for name, models in SUBSETS.items():
            chosen = [row for row in group if row["model"] in models]
            if (len(chosen) != len(models) or {r["model"] for r in chosen} != set(models)
                    or any("judge_run" not in row for row in chosen)):
                continue  # Missing planned records are not reconstructed into votes.
            judges = tuple(JudgeRun.model_validate_json(json.dumps(row["judge_run"]))
                           for row in chosen)
            audits = tuple(JudgeValidationRun.model_validate_json(json.dumps(row["validation"]))
                           for row in chosen if row.get("validation"))
            request = AggregationInput(
                claim_id=pack.claim_id, evidence_pack_id=pack_id,
                evidence_pack_hash=pack.snapshot_hash,
                judge_run_ids=tuple(j.judge_run_id for j in judges),
                judge_validation_run_ids=tuple(a.id for a in audits),
                mode=AggregationMode.FIXTURE_OR_EVALUATION, policy_version=POLICY_V4.version,
            )
            context = AggregationContext(
                claim=ClaimFacts(claim_id=pack.claim_id, normalization_status="normalized",
                                 risk_class="standard"),
                pack=pack, stored_pack_hash=pack.snapshot_hash, retrieval_status="ok",
                judges=judges, validations=audits,
            )
            verdict = VerdictService(POLICY_V4).aggregate(request, context)
            expected = chosen[0].get("expected_position")
            results.append({
                "case_id": identifier, "split": case.split, "architecture": architecture,
                "repeat": repeat, "subset": name, "verdict": str(verdict.verdict),
                "expected_position": expected, "qualified_judges": verdict.qualified_judges,
                "reasons": [str(r) for r in verdict.reason_codes],
                "production_qualified": verdict.production_qualified,
            })
    metrics = {}
    for architecture, subset in sorted({(r["architecture"], r["subset"]) for r in results}):
        splits = {}
        for split in ("all", "development", "held_out"):
            rows = [r for r in results if r["architecture"] == architecture
                    and r["subset"] == subset and (split == "all" or r["split"] == split)]
            splits[split] = {
                "count": len(rows), "verdicts": dict(Counter(r["verdict"] for r in rows)),
                "false_decisive": sum(r["verdict"] in {"supported", "contradicted"}
                                      and r["verdict"] != r["expected_position"] for r in rows),
                "position_agreement": sum(r["verdict"] == r["expected_position"] for r in rows),
                "production_qualified": sum(r["production_qualified"] for r in rows),
            }
        metrics[f"{architecture}:{subset}"] = splits
    return {"version": "offline-lens-subsets-1.0", "purge_after": artifact["purge_after"],
            "clinical_qualification": False, "identity_verified": False,
            "policy_version": POLICY_V4.version, "policy_changed": False,
            "single_model_note": "Lite is a measured baseline, not an established strongest model",
            "missing_records": "excluded; no manufactured votes", "rows": results,
            "metrics": metrics}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--runtime", type=Path, default=Path("../runtime"))
    args = parser.parse_args()
    settings = Settings(_env_file="../.env")  # type: ignore[call-arg]
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Development/test only")
    result = compare(load_retained(args.artifact))
    print(save_artifact(runtime_directory(args.runtime), "ensemble", result, settings))
    for key, splits in result["metrics"].items():
        print(key, splits)


if __name__ == "__main__":
    main()
