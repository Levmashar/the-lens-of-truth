"""Read-only export of the retained Slice 1 conclusion blocker, not a rerun."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.diagnostics import diagnostic_secrets, sanitize_diagnostic


def capture_blocker(runtime: Path) -> dict[str, Any]:
    paths = sorted((runtime / "reliability").glob("slice1-eval-*.json"))
    if not paths:
        raise ValueError("No retained Slice 1 evaluation traces")
    final = json.loads(paths[-1].read_text(encoding="utf-8"))
    if datetime.fromisoformat(final["purge_after"]) <= datetime.now(UTC):
        raise ValueError("Original traces expired; do not reconstruct them as originals")
    output: dict[str, Any] = {
        "contract": "slice2-blocker-replay-1.0", "original_artifacts": True,
        "purge_after": final["purge_after"], "network_calls": 0,
        "historical_rows_modified": False, "probes": [],
        "classification_origin": "engineering inspection of exact retained trace",
    }
    for probe in final["frozen_runs"]:
        revision = probe.get("revision")
        judge = revision["judge"] if revision else probe["judge"]
        validation = revision["validation"] if revision else probe["validation"]
        result = validation["result"]
        conclusion = result["conclusion_justification"]
        active_id = judge["judge_run_id"]
        calls = []
        repeats = []
        for path in paths:
            trace = json.loads(path.read_text(encoding="utf-8"))
            if trace.get("purge_after") and datetime.fromisoformat(
                trace["purge_after"]
            ) <= datetime.now(UTC):
                continue
            for call in trace.get("call_diagnostics", []):
                messages = call.get("messages") or []
                if not messages or "validated_findings" not in messages[-1].get("content", ""):
                    continue
                if trace is final or path == paths[-1]:
                    calls.append(call)
            for previous in trace.get("frozen_runs", []):
                if previous.get("analysis_id") != probe["analysis_id"]:
                    continue
                audits = [("parent", previous.get("validation"))]
                if previous.get("revision"):
                    audits.append(("revision", previous["revision"].get("validation")))
                for kind, audit in audits:
                    if audit:
                        repeats.append({
                            "trace": path.name, "kind": kind,
                            "judge_run_id": audit["judge_run_id"],
                            "conclusion": audit["result"].get("conclusion_justification"),
                            "identical_findings_not_assumed": True,
                        })
        # Match the exact concluding request to this active judge's findings.
        texts = [s["text"] for s in judge["decision"]["statements"]]
        exact_calls = [call for call in calls if all(
            text in call["messages"][-1]["content"] for text in texts
        )]
        output["probes"].append({
            "analysis_id": probe["analysis_id"], "active_judge_run_id": active_id,
            "claim": judge["input_snapshot_json"]["claim"],
            "proposed_label": judge["decision"]["label"],
            "statements": judge["decision"]["statements"],
            "source_attributions": result["statement_attributions"],
            "old_conclusion_requests": exact_calls, "conclusion": conclusion,
            "repeated_outcomes": repeats,
            "confirmed_categories": ["B_status_rationale_contradiction"],
            "contributing_categories": ["C_scope_ambiguity", "D_evidence_strength_ambiguity"],
            "unconfirmed_categories": ["E_same_input_provider_instability"],
            "classification_note": (
                "All active findings were attributed. The proposed inconclusive label was "
                "rejected while the rationale describes insufficiency compatible with it. "
                "Earlier probes used the same Pack but different judge findings; those are "
                "not controlled identical-input stability trials. No active transport/schema "
                "failure is present. This does not establish a medical claim label."
            ),
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=Path("../runtime"))
    args = parser.parse_args()
    settings_args: dict[str, Any] = {"_env_file": "../.env"}
    settings = Settings(**settings_args)
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Development/test only")
    runtime = args.runtime.resolve()
    if runtime.name != "runtime":
        raise SystemExit("Use the ignored repository runtime directory")
    artifact = sanitize_diagnostic(capture_blocker(runtime), diagnostic_secrets(settings))
    directory = runtime / "debug"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"slice2-blocker-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.json"
    with target.open("x", encoding="utf-8") as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2)
    for probe in artifact["probes"]:
        print(probe["analysis_id"], probe["proposed_label"],
              probe["conclusion"]["status"], len(probe["old_conclusion_requests"]))
    print(target)


if __name__ == "__main__":
    main()
