"""Offline replay of measured relations through the pure qualifier, not clinical truth."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.judging.models import JudgeLabel
from app.validation.qualification import (
    ConclusionQualifierInput,
    FindingQualificationInput,
    qualify_conclusion,
)
from app.validation.relation_cases import CASES, HUMAN_REVIEWED, RelationCase
from app.validation.relation_flow import claim_magnitude_alignment
from app.validation.relations import (
    ClaimRelationAssessment,
    canonical_hash,
    prepare_relation_input,
)


def qualification_input(
    case: RelationCase, relation: ClaimRelationAssessment, label: JudgeLabel,
) -> ConclusionQualifierInput:
    return ConclusionQualifierInput(
        proposed_label=label, claim_type=case.claim_type, risk_class="standard",
        findings=(FindingQualificationInput(
            statement_id="S1", study_designs=(case.study_design,),
            claim_magnitude_alignment=claim_magnitude_alignment(case.claim, case.statement),
            integrity_statuses=("valid",),
        ),),
        relations=(relation,), based_on_statement_ids=("S1",),
    )


def evaluate(artifact: dict[str, Any]) -> dict[str, Any]:
    cases = {case.id: case for case in CASES}
    output: dict[str, Any] = {
        "origin": "offline conditional qualification of saved relation benchmark",
        "human_reviewed": HUMAN_REVIEWED, "clinical_qualification": False,
        "model_calls": 0, "oracle": "engineer annotations plus unchanged qualifier gates",
        "models": [],
    }
    for model in artifact["models"]:
        rows = []
        for measured in model["baseline"]:
            case = cases[measured["case_id"]]
            expected_input = {**case.payload(), "required_statement_ids": ("S1",)}
            if canonical_hash(expected_input) != canonical_hash(measured["input"]):
                raise ValueError("Measured input differs from the frozen benchmark case")
            versions = ([artifact["relation_prompt_version"]]
                        if artifact.get("relation_prompt_version") else [
                            f"claim-relation-{version}-2026-10-01"
                            for version in ("1.0", "1.1", "1.2")
                        ])
            if not any(prepare_relation_input(
                case.payload(), judge_run_id="benchmark", validation_run_id="benchmark",
                statement_ids=("S1",), prompt_version=version,
            ).prompt_hash == measured["prompt_hash"] for version in versions):
                raise ValueError("Measured relation prompt hash is not reconstructible")
            expected = ClaimRelationAssessment(
                statement_id="S1", relation=case.expected, scope=case.scope,
                materiality=case.materiality, reason=case.rationale,
            )
            response = (ClaimRelationAssessment.model_validate_json(
                            json.dumps(measured["response"]),
                        )
                        if measured.get("response") else None)
            for label in JudgeLabel:
                expected_output = qualify_conclusion(qualification_input(case, expected, label))
                actual_output = (qualify_conclusion(qualification_input(case, response, label))
                                 if response else None)
                rows.append({
                    "case_id": case.id, "proposed_label": label,
                    "expected_qualified": expected_output.status == "justified",
                    "actual_qualified": bool(actual_output and actual_output.status == "justified"),
                    "output": actual_output.model_dump(mode="json") if actual_output else None,
                    "operational_failure": measured.get("failure"),
                })
        positives = [r for r in rows if r["expected_qualified"]]
        negatives = [r for r in rows if not r["expected_qualified"]]
        decisive_negatives = [r for r in negatives if r["proposed_label"] != "not_enough_evidence"]
        output["models"].append({
            "model": model["model"], "proposals": len(rows),
            "false_qualified": sum(r["actual_qualified"] for r in negatives),
            "negative_proposals": len(negatives),
            "false_decisive_qualified": sum(r["actual_qualified"] for r in decisive_negatives),
            "negative_decisive_proposals": len(decisive_negatives),
            "false_rejected": sum(not r["actual_qualified"] for r in positives),
            "positive_proposals": len(positives), "rows": rows,
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    path = args.artifact.resolve()
    if path.parent.name != "debug" or path.parent.parent.name != "runtime":
        raise SystemExit("Read an ignored runtime/debug benchmark artifact")
    output = evaluate(json.loads(path.read_text(encoding="utf-8")))
    destination = path.parent / f"slice2-qualification-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.json"
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    for model in output["models"]:
        print(json.dumps({k: v for k, v in model.items() if k != "rows"}))
    print(destination)


if __name__ == "__main__":
    main()
