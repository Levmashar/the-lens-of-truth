"""Read-only per-selected-source chain from a retained, sanitized original capture."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.retrieval.analysis_design import characterize_analysis
from app.retrieval.models import EvidencePack


def trace(captured: dict[str, Any]) -> dict[str, Any]:
    if captured.get("availability") != "retained_original":
        raise ValueError("Retained original required; reconstructed fixtures are not originals")
    if datetime.fromisoformat(captured["purge_after"]) <= datetime.now(UTC):
        raise ValueError("Original expired; do not resurrect it")
    output: dict[str, Any] = {
        "analysis_id": captured["analysis_id"], "origin": "retained_original",
        "purge_after": captured["purge_after"], "historical_records_changed": False,
        "documents": [], "verdicts": [],
    }
    for item in captured["claims"]:
        pack = EvidencePack.model_validate(item["pack"]["snapshot_json"])
        active = set(item["checkpoint"]["judge_run_ids"])
        documents = {d.document_id: d for d in pack.documents}
        for ranked in pack.passages:
            if ranked.evidence_id not in pack.selected_evidence_ids:
                continue
            doc = documents[ranked.passage.document_id]
            siblings = {p.evidence_id for p in pack.passages
                        if p.passage.document_id == doc.document_id}
            judges = []
            for judge in item["judges"]:
                if judge["id"] not in active:
                    continue
                snapshot = judge.get("input_snapshot_json") or {}
                decision = judge.get("decision_json") or {}
                findings = [s for s in decision.get("statements", [])
                            if any(r["evidence_id"] in siblings for r in s["evidence_refs"])]
                audits = [a for a in item["validations"] if a["judge_run_id"] == judge["id"]]
                judges.append({
                    "judge_id": judge["id"], "slot": judge["slot"], "label": decision.get("label"),
                    "visible_ids": sorted(siblings & set(
                        snapshot.get("judge_visible_evidence_ids", []))), "findings": findings,
                    "validation": [{"id": a["id"], "status": a["status"],
                                    "attribution": a["result_json"].get("statement_attributions"),
                                    "relations": a["result_json"].get("relation_validation"),
                                    "qualifier": a["result_json"].get("conclusion_qualification")}
                                   for a in audits],
                })
            output["documents"].append({
                "document": doc.model_dump(mode="json"), "evidence_id": ranked.evidence_id,
                "queries": [q.model_dump(mode="json") for q in pack.query_plan.queries
                            if q.query_id in doc.query_ids], "candidate_pmid": doc.pmid,
                "rank": ranked.rank, "retrieval_score": ranked.retrieval_score,
                "priority": ranked.selection_priority_score, "selection": ranked.selection_reason,
                "corrected_design_read_only": characterize_analysis(
                    pack.claim_snapshot, doc).model_dump(mode="json"), "judges": judges,
            })
        output["verdicts"].append((item.get("verdict") or {}).get("result_json"))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    runtime = Path(__file__).resolve().parents[3] / "runtime"
    if not args.capture.resolve().is_relative_to(runtime):
        raise SystemExit("Read only an ignored runtime capture")
    output = trace(json.loads(args.capture.read_text(encoding="utf-8")))
    target = runtime / "debug" / f"slice3-smoking-trace-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.json"
    with target.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(target)


if __name__ == "__main__":
    main()
