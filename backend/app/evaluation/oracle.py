"""Offline reviewed development selection from actual frozen sources, never production."""

import argparse
import json
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.evaluation.artifacts import load_retained, runtime_directory, save_artifact
from app.evaluation.cases import benchmark_cases
from app.evaluation.selection import lean_selection, oracle_selection
from app.retrieval.models import EvidencePack


def prepare(artifact: dict[str, Any], reviewed: dict[str, list[str]]) -> dict[str, Any]:
    claims = []
    selections = []
    for claim in artifact["claims"]:
        if not claim.get("pack"):
            continue
        pack = EvidencePack.model_validate(claim["pack"]["snapshot_json"])
        identifier = str(pack.claim_id)
        # Fresh control origins are preserved, never recast as historical runs.
        claims.append(claim)
        if identifier not in reviewed:
            continue
        oracle = oracle_selection(pack, tuple(reviewed[identifier]))
        lean = lean_selection(pack)
        ids = {p.passage.document_id for p in oracle.passages if p.selected_for_judging}
        variants: dict[str, Any] = {}
        for name, chosen in (("current", pack), ("lean", lean), ("oracle", oracle)):
            selected = {p.passage.document_id for p in chosen.passages if p.selected_for_judging}
            variants[name] = {
                "hash": chosen.snapshot_hash, "selected_documents": sorted(selected),
                "reviewed_relevant_recall": len(selected & ids) / len(ids),
                "reviewed_selected_precision": len(selected & ids) / len(selected)
                if selected else 0,
            }
        selections.append({"case_id": identifier, "variants": variants})
    for case in benchmark_cases():
        if case.id in {"numeric-overclaim", "association-causal", "precise-magnitude-null",
                       "conflict-positive"}:
            claims.append({"pack": {"snapshot_json": case.pack.model_dump(mode="json")},
                           "origin": case.origin, "case_id": case.id})
    return {"version": "source-baseline-15-1.0", "purge_after": artifact["purge_after"],
            "origin": "fresh public-source controls plus four explicitly synthetic controls",
            "review_method": "engineer inspected retrieved abstracts and causal source blocks",
            "clinical_qualification": False, "independent_human_review": False,
            "claims": claims, "oracle_comparison": selections}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("selection", type=Path)
    parser.add_argument("--runtime", type=Path, default=Path("../runtime"))
    args = parser.parse_args()
    settings = Settings(_env_file="../.env")  # type: ignore[call-arg]
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Development/test only")
    artifact = load_retained(args.capture)
    reviewed = json.loads(args.selection.read_text(encoding="utf-8"))
    result = prepare(artifact, reviewed)
    print(save_artifact(runtime_directory(args.runtime), "source-baseline", result, settings))
    print(json.dumps(result["oracle_comparison"]))


if __name__ == "__main__":
    main()
