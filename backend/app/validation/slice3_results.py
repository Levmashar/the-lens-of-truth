"""Read-only aggregate paired development measurements; no medical relabeling."""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def summarize(data: dict[str, Any]) -> list[dict[str, Any]]:
    calls = [c for c in data["budget"]["calls"] if c.get("model")]
    cursor = 0
    rows = []
    for case in data["cases"]:
        for variant in case["variants"]:
            used = calls[cursor : cursor + variant["http_calls"]]
            cursor += variant["http_calls"]
            artifact = variant["artifact"]["claims"][0]
            pack = (artifact.get("pack") or {}).get("snapshot_json") or {}
            selected_docs = {p["document_id"] for p in variant["selected"]}
            docs = pack.get("documents", [])
            selected = [d for d in docs if d["document_id"] in selected_docs]
            verdict = (artifact.get("verdict") or {}).get("result_json") or {}
            active_audits = set(artifact["checkpoint"]["validation_run_ids"])
            active_judges = set(artifact["checkpoint"]["judge_run_ids"])
            audits = [a for a in artifact["validations"] if a["id"] in active_audits]
            judges = [j for j in artifact["judges"] if j["id"] in active_judges]
            issue_counts = Counter(
                i["issue_code"] for a in audits for i in a["result_json"].get("targeted_issues", [])
            )
            rows.append(
                {
                    "case": case["number"],
                    "claim": case["claim"],
                    "variant": variant["name"],
                    "analysis_id": variant["analysis_id"],
                    "status": variant["status"],
                    "pubmed_documents": sum(d["source_kind"] == "pubmed" for d in docs),
                    "authoritative_documents": sum(bool(d.get("authoritative")) for d in docs),
                    "selected_roles": dict(
                        Counter(d.get("evidence_role_hint") or "legacy_direct" for d in selected)
                    ),
                    "selected_sources": [
                        {
                            "id": d["document_id"],
                            "title": d["title"],
                            "role": d.get("evidence_role_hint"),
                            "analysis": d.get("relationship_analysis"),
                            "purpose": (d.get("authoritative") or {}).get("document_purpose"),
                        }
                        for d in selected
                    ],
                    "sentinel_trace": [
                        {
                            "pmid": p,
                            "candidate": any(p in q["pmids"] for q in case["search_executions"]),
                            "normalized": any(d["pmid"] == p for d in docs),
                            "selected": any(d["pmid"] == p for d in selected),
                        }
                        for p in (
                            ("38268471",)
                            if case["number"] in {1, 2}
                            else ("21135266", "29620003")
                            if case["number"] == 3
                            else ()
                        )
                    ],
                    "qualified": verdict.get("qualified_judges"),
                    "verdict": verdict.get("verdict"),
                    "reason_codes": verdict.get("reason_codes"),
                    "issues": dict(issue_counts),
                    "judge_failures": [
                        (j["slot"], j["error_category"]) for j in judges if j["error_category"]
                    ],
                    "validation_statuses": [a["status"] for a in audits],
                    "latency_seconds": variant["latency_seconds"],
                    "model_http_calls": len(used),
                    "input_tokens": sum(
                        c.get("usage", {}).get("prompt_tokens", 0) or 0 for c in used
                    ),
                    "output_tokens": sum(
                        c.get("usage", {}).get("completion_tokens", 0) or 0 for c in used
                    ),
                    "source_fetch_seconds": case["source_fetch_seconds"],
                    "source_statuses": case["authoritative_statuses"],
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    runtime = Path(__file__).resolve().parents[3] / "runtime"
    if not args.artifact.resolve().is_relative_to(runtime):
        raise SystemExit("Read only ignored runtime artifacts")
    print(
        json.dumps(
            summarize(json.loads(args.artifact.read_text(encoding="utf-8"))),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
