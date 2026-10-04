"""Counterfactual new qualification of retained, already attributed Slice 1 findings."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.adapters.entailment import OpenAICompatibleEntailmentValidator
from app.core.config import Settings
from app.core.diagnostics import diagnostic_secrets, sanitize_diagnostic
from app.judging.config import configured_slots, is_search_enabled_model
from app.judging.models import JudgeDecisionV2, JudgeRun
from app.judging.prompt import input_snapshot_hash, prepare_judge_input
from app.judging.source_units import materialize_content
from app.retrieval.models import EvidencePack
from app.validation.evaluation_budget import EvaluationBudget
from app.validation.models import JudgeValidationRun, StatementAttributionStatus
from app.validation.relation_flow import qualify_with_relations


async def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    settings_args: dict[str, Any] = {"_env_file": "../.env"}
    settings = Settings(**settings_args)
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Development/test only")
    runtime = args.runtime.resolve()
    traces = sorted((runtime / "reliability").glob("slice1-eval-*.json"))
    trace = json.loads(traces[-1].read_text(encoding="utf-8"))
    if datetime.fromisoformat(trace["purge_after"]) <= datetime.now(UTC):
        raise SystemExit(
            "Original traces expired; reconstructed fixtures must be labeled separately",
        )
    budget = EvaluationBudget(args.max_calls, args.deadline)
    output: dict[str, Any] = {
        "origin": "counterfactual qualification of retained source-attributed findings",
        "historical_rows_modified": False, "new_judge_calls": 0,
        "purge_after": trace["purge_after"], "results": [], "clinical_qualification": False,
    }
    slots = [s for s in configured_slots(settings) if not is_search_enabled_model(s.model)
             and (not args.slot or s.slot in args.slot)]
    try:
        with budget.measure():
            async with asyncio.timeout(args.deadline):
                for probe in trace["frozen_runs"]:
                    captures = sorted((runtime / "reliability").glob(
                        f"{probe['analysis_id']}-*.json"))
                    capture = json.loads(captures[-1].read_text(encoding="utf-8"))
                    if datetime.fromisoformat(capture["purge_after"]) <= datetime.now(UTC):
                        raise ValueError("Original capture expired")
                    pack = EvidencePack.model_validate(
                        capture["claims"][0]["pack"]["snapshot_json"],
                    )
                    active = probe.get("revision") or probe
                    old_judge = JudgeRun.model_validate_json(json.dumps(active["judge"]))
                    old_validation = JudgeValidationRun.model_validate(active["validation"])
                    assert old_judge.input_snapshot_version is not None
                    assert old_judge.input_snapshot_json is not None
                    original = prepare_judge_input(old_judge.evidence_pack_id, pack,
                                                   version=old_judge.input_snapshot_version)
                    if (old_judge.input_snapshot_hash != original.input_snapshot_hash
                            or input_snapshot_hash(old_judge.input_snapshot_json)
                            != original.input_snapshot_hash
                            or any(
                                a.status != StatementAttributionStatus.SUPPORTED_BY_SOURCES
                                or a.issues for a in old_validation.result.statement_attributions
                            )):
                        raise ValueError("Retained attribution provenance not complete")
                    prepared = prepare_judge_input(old_judge.evidence_pack_id, pack)
                    decision = old_judge.decision
                    assert isinstance(decision, JudgeDecisionV2)
                    wire = {
                        "label": decision.label,
                        "statements": [{"statement_id": s.statement_id, "text": s.text,
                                        "kind": s.kind, "source_unit_ids": s.source_unit_ids}
                                       for s in decision.statements],
                        "conclusion": decision.conclusion.model_dump(mode="json"),
                        "uncertainty_reasons": decision.uncertainty_reasons,
                    }
                    new_judge = old_judge.model_copy(update={
                        "judge_run_id": uuid4(), "decision": materialize_content(
                            json.dumps(wire), prepared.input_snapshot_json),
                        "input_snapshot_version": prepared.input_snapshot_version,
                        "input_snapshot_hash": prepared.input_snapshot_hash,
                        "input_snapshot_json": prepared.input_snapshot_json,
                    })
                    for slot in slots:
                        validator = OpenAICompatibleEntailmentValidator(
                            slot.provider, slot.model, slot.base_url, slot.api_key, 18,
                        )
                        conclusion, relation, qualifier, _ = await qualify_with_relations(
                            new_judge, pack, old_validation.result.statement_attributions,
                            validator, uuid4(),
                            risk_class=capture["claims"][0]["claim"]["risk_class"],
                        )
                        record = {
                            "analysis_id": probe["analysis_id"], "pack_hash": pack.snapshot_hash,
                            "original_active_judge_id": str(old_judge.judge_run_id),
                            "validator_slot": slot.slot, "validator_model": slot.model,
                            "claim": pack.claim_snapshot.standalone_text,
                            "proposed_label": decision.label,
                            "source_attributions": [a.model_dump(mode="json") for a in
                                                    old_validation.result.statement_attributions],
                            "relation": relation.model_dump(mode="json"),
                            "qualification": qualifier.model_dump(mode="json"),
                            "conclusion_status": conclusion.status,
                        }
                        output["results"].append(record)
                        print(probe["analysis_id"], slot.model, conclusion.status, flush=True)
    except TimeoutError:
        budget.failure = "evaluation_deadline_exceeded"
    output["budget"] = budget.summary()
    return dict(sanitize_diagnostic(output, diagnostic_secrets(settings)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--runtime", type=Path, default=Path("../runtime"))
    parser.add_argument("--slot", type=int, choices=(1, 2, 3), action="append")
    parser.add_argument("--max-calls", type=int, default=12)
    parser.add_argument("--deadline", type=float, default=150)
    args = parser.parse_args()
    if not args.run or not (1 <= args.max_calls <= 24 and 1 <= args.deadline <= 180):
        raise SystemExit("Opt in with --run and bounded calls/deadline")
    if args.runtime.resolve().name != "runtime":
        raise SystemExit("Use ignored runtime directory")
    output = asyncio.run(evaluate(args))
    directory = args.runtime.resolve() / "debug"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"slice2-frozen-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(path)
    if output["budget"]["failure"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
