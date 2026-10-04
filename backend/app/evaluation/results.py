"""Offline measured summary; failed calls stay in denominators, never medical gold."""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.evaluation.artifacts import load_retained, runtime_directory, save_artifact
from app.evaluation.judge_bakeoff import row_metrics


def repeatability(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["case_id"], row["model"], row["architecture"], row.get("selection", "current"))
        groups.setdefault(key, []).append(row)
    return {"|".join(key): {
        "repeats": len(group), "identical_input": len({r.get("input_hash") for r in group}) == 1,
        "position_distribution": dict(Counter(str(r.get("position")) for r in group)),
        "relation_distribution": dict(Counter(str(r.get("relation")) for r in group)),
        "position_flips": sum(a.get("position") != b.get("position")
                              for a, b in zip(group, group[1:], strict=False)),
        "relation_flips": sum(a.get("relation") != b.get("relation")
                              for a, b in zip(group, group[1:], strict=False)),
        "flip_denominator": len(group) - 1,
        "failures": dict(Counter(r["failure"] for r in group if r.get("failure"))),
    } for key, values in groups.items()
       if len(group := sorted(values, key=lambda r: r["repeat"])) > 1}


def summarize(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    experiments = []
    for data in artifacts:
        rows = data["rows"]
        groups = sorted({(r["model"], r["architecture"]) for r in rows})
        experiments.append({
            "rows": len(rows), "http_statuses": dict(Counter(
                str(c.get("http_status")) for c in data["budget"]["calls"])),
            "input_tokens": data["budget"]["input_tokens"],
            "output_tokens": data["budget"]["output_tokens"],
            "calls": data["budget"]["http_calls"], "failure": data["budget"]["failure"],
            "models": {f"{m}:{a}": {split: row_metrics([r for r in rows if
                r["model"] == m and r["architecture"] == a and
                (split == "all" or r["split"] == split)])
                for split in ("all", "development", "held_out")} for m, a in groups},
            "false_decisive_rows": [{k: r.get(k) for k in ("case_id", "model", "architecture",
                                      "position", "expected_position", "relation", "scope")}
                                    for r in rows if r.get("expected_position") is not None and
                                    r.get("position") in {"supported", "contradicted"} and
                                    r["position"] != r["expected_position"]],
            "identity_fingerprints_returned": sum(bool(r.get("system_fingerprint")) for r in rows),
            "repeatability": repeatability(rows),
        })
    return {"version": "bakeoff-summary-1.0", "clinical_qualification": False,
            "identity_verified": False, "experiments": experiments,
            "purge_after": min(d["purge_after"] for d in artifacts)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path, nargs="+")
    parser.add_argument("--runtime", type=Path, default=Path("../runtime"))
    args = parser.parse_args()
    result = summarize([load_retained(p) for p in args.artifacts])
    settings = Settings(_env_file="../.env")  # type: ignore[call-arg]
    print(save_artifact(runtime_directory(args.runtime), "summary", result, settings))
    for data in result["experiments"]:
        print(json.dumps({k: data[k] for k in ("rows", "http_statuses", "calls", "failure")}))
        for model, splits in data["models"].items():
            all_rows = splits["all"]
            print(model, json.dumps({k: all_rows[k] for k in (
                "schema_success", "usable", "relation_agreement", "false_support_position",
                "false_contradiction_position", "numeric_issues", "calls", "p50_latency_ms")}))


if __name__ == "__main__":
    main()
