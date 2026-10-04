"""Bounded fresh V2 assessments of retained identical Packs, not semantic revisions."""

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID

from app.adapters.entailment import OpenAICompatibleEntailmentValidator
from app.adapters.judge import OpenAICompatibleJudgeProvider
from app.core.config import Settings
from app.evaluation.artifacts import load_retained, runtime_directory, save_artifact
from app.judging.config import configured_slots
from app.judging.service import JudgeService
from app.pipeline.readiness import ready_for_evidence
from app.retrieval.models import EvidencePack
from app.validation.joint23 import validate_joint23
from app.verdict.models import AggregationContext, AggregationInput, AggregationMode, ClaimFacts
from app.verdict.policy import POLICY_V4
from app.verdict.service import VerdictService


async def run(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    slots = configured_slots(settings)
    checker = next(s for s in slots if s.slot == 3)
    validator = OpenAICompatibleEntailmentValidator(
        provider=checker.provider, model=checker.model, base_url=checker.base_url,
        api_key=checker.api_key, timeout_seconds=25,
    )
    rows: list[dict[str, Any]] = []
    captures = [(path, load_retained(path)) for path in args.capture]
    expiry = min(datetime.fromisoformat(c["purge_after"]) for _, c in captures)
    for path, capture in captures:
        for item in capture["claims"]:
            if not item["pack"] or not item["verdict"]:
                raise ValueError("A retained complete Pack and verdict are required")
            pack = EvidencePack.model_validate(item["pack"]["snapshot_json"])
            pack_id = UUID(item["pack"]["id"])
            claim = item["claim"]
            facts = ClaimFacts(
                claim_id=pack.claim_id, normalization_status=claim["normalization_status"],
                risk_class=claim["risk_class"], normalization_reviewed=ready_for_evidence(
                    claim["normalization_status"], pico_json=claim["pico_json"],
                    quality_json=claim["normalization_quality"],
                    standalone_status=claim["standalone_status"],
                    standalone_text=claim["normalized_text"],
                ),
            )
            for repeat in range(args.repeats):
                if datetime.now(UTC) >= expiry:
                    raise ValueError("Capture expired; do not extend TTL")
                start = monotonic()
                judges, _ = await JudgeService(
                    providers={"openai_compatible": OpenAICompatibleJudgeProvider(45)},
                    axes_development=True,
                ).run(
                    pack_id, pack, slots, app_env=settings.app_env,
                    allow_search_enabled_development=settings.judge_allow_search_enabled_development,
                )
                validations = tuple(await asyncio.gather(*(
                    validate_joint23(j, pack, validator, risk_class=facts.risk_class)
                    for j in judges if j.decision is not None
                )))
                request = AggregationInput(
                    claim_id=pack.claim_id, evidence_pack_id=pack_id,
                    evidence_pack_hash=pack.snapshot_hash,
                    judge_run_ids=tuple(j.judge_run_id for j in judges),
                    judge_validation_run_ids=tuple(v.id for v in validations),
                    mode=AggregationMode.FIXTURE_OR_EVALUATION, policy_version=POLICY_V4.version,
                )
                context = AggregationContext(
                    claim=facts, pack=pack, stored_pack_hash=pack.snapshot_hash,
                    stored_pack_version=pack.evidence_pack_version,
                    stored_pack_claim_id=pack.claim_id,
                    retrieval_status=item["retrieval"]["status"], judges=judges,
                    validations=validations,
                )
                verdict = VerdictService(POLICY_V4).aggregate(request, context)
                row = {"capture": path.name, "original_analysis_id": capture["analysis_id"],
                       "input": pack.claim_snapshot.standalone_text, "repeat": repeat + 1,
                       "pack_hash": pack.snapshot_hash,
                       "judges": [j.model_dump(mode="json") for j in judges],
                       "validations": [v.model_dump(mode="json") for v in validations],
                       "verdict": verdict.model_dump(mode="json"),
                       "latency_ms": round((monotonic() - start) * 1000)}
                rows.append(row)
                save_artifact(runtime_directory(args.runtime), "slice41-repeat-row",
                              {"purge_after": expiry.isoformat(), "row": row}, settings)
                print({"claim": row["input"], "repeat": repeat + 1,
                       "verdict": str(verdict.verdict), "qualified": verdict.qualified_judges,
                       "latency_ms": row["latency_ms"]}, flush=True)
    return {"version": "slice41-repeatability-1.0", "purge_after": expiry.isoformat(),
            "clinical_qualification": False, "database_mutated": False, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--capture", type=Path, action="append", required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--runtime", type=Path, default=Path("../runtime"))
    args = parser.parse_args()
    settings = Settings(_env_file="../.env")  # type: ignore[call-arg]
    if not args.run or settings.app_env not in {"development", "test"} or not (
        1 <= len(args.capture) <= 3 and 1 <= args.repeats <= 2
    ):
        raise SystemExit("Opt in to 1-3 retained cases and at most two fresh repeats")
    print(save_artifact(runtime_directory(args.runtime), "slice41-repeatability",
                        asyncio.run(run(args, settings)), settings))


if __name__ == "__main__":
    main()
