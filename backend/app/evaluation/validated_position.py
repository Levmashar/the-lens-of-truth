"""Read-only four-case saved-response replay. No database writes or provider calls."""

import argparse
import asyncio
import gzip
import json
from pathlib import Path
from typing import TypedDict

from app.judging.compact24 import frozen_response_matches24
from app.judging.compact25 import prepare_compact25
from app.judging.models import JudgeDecisionV2, JudgeRun
from app.judging.source_units import materialize_content
from app.retrieval.models import EvidencePack
from app.validation.audit25 import audit_matches25
from app.validation.joint23 import JointResponse23
from app.validation.joint24 import validate_joint24


class SavedResponse:
    provider = "paratera"
    model = "ERNIE-4.5-Turbo-128K"

    def __init__(self, response: JointResponse23) -> None:
        self.response = response

    async def assess_joint23(self, prepared: object) -> JointResponse23:
        return self.response


class ReplayResult(TypedDict):
    contract: str
    paid_model_calls: int
    historical_rows_updated: int
    results: list[dict[str, object]]


async def replay(path: Path) -> ReplayResult:
    """Explicit in-memory adoption replay; original V2.4 rows stay V2.4."""
    frozen = json.loads(gzip.decompress(path.read_bytes()))
    results: list[dict[str, object]] = []
    for case, row in frozen.items():
        pack = EvidencePack.model_validate(row["pack"])
        for source in (row, *row.get("variants", [])):
            original = JudgeRun.model_validate_json(json.dumps(source["judge"]))
            if not frozen_response_matches24(original, pack):
                raise ValueError("Saved historical input/response identity mismatch")
            assert original.response_json is not None
            assert isinstance(original.decision, JudgeDecisionV2)
            prepared = prepare_compact25(original.evidence_pack_id, pack)
            raw = original.response_json["raw_model_content"]
            assert isinstance(raw, str)
            decision = materialize_content(raw, prepared.input_snapshot_json)
            judge = original.model_copy(update={
                "decision": decision,
                "response_json": {**decision.model_dump(mode="json"), "raw_model_content": raw},
                "input_snapshot_version": prepared.input_snapshot_version,
                "input_snapshot_hash": prepared.input_snapshot_hash,
                "input_snapshot_json": prepared.input_snapshot_json,
                "prompt_version": prepared.prompt_version, "prompt_hash": prepared.prompt_hash,
            })
            old_result = source["validation_result"]
            response = JointResponse23.model_validate_json(json.dumps(
                old_result["relation_validation"]["joint_response"]))
            audit = await validate_joint24(judge, pack, SavedResponse(response))
            results.append({
                "case": case, "model": original.model,
                "saved_judge_run_id": str(original.judge_run_id),
                "frozen_pack_hash": pack.snapshot_hash,
                "original_model_proposal": original.decision.label,
                "original_validation_status": old_result["validation_status"],
                "validated_evidence_position": audit.result.validated_evidence_position,
                "validation_status": audit.status,
                "audit_reconstruction_matches": audit_matches25(judge, audit, pack, "standard"),
                "position_audit": audit.result.conclusion_qualification,
            })
    return {"contract": "judge-validation-2.5", "paid_model_calls": 0,
            "historical_rows_updated": 0, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(replay(args.input))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in result["results"]:
        print(f"{row['case']} / {row['model']}: {row['original_model_proposal']} -> "
              f"{row['validated_evidence_position']} (audit={row['audit_reconstruction_matches']})")


if __name__ == "__main__":
    main()
