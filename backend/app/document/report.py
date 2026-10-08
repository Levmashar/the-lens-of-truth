"""Readable document projection of validated items; never a generated truth score."""

from typing import Any
from uuid import UUID

from app.document.evaluation import aggregate_positions, is_reporting
from app.document.models import DocumentPlan
from app.judging.source_units import SourceUnit
from app.retrieval.models import EvidencePack

VERSION = "document-report-1.0"


def build_document_report(
    analysis_id: UUID,
    plan: DocumentPlan,
    evidence: dict[str, dict[str, Any]],
    runs: dict[str, list[dict[str, Any]]],
    *,
    app_env: str,
    status: str,
    failures: dict[str, str] | None = None,
) -> dict[str, Any]:
    groups = []
    completed = 0
    groups_completed = 0
    for group in plan.groups:
        saved = evidence.get(group.group_id)
        source_match = saved.get("source_match", {}) if saved else {}
        pack = EvidencePack.model_validate(saved["pack"]) if saved else None
        docs = {d.document_id: d for d in pack.documents} if pack else {}
        units = (
            {
                u.unit_id: u
                for u in (SourceUnit.model_validate(item) for item in saved.get("source_units", []))
            }
            if saved
            else {}
        )
        group_runs = runs.get(group.group_id, [])
        checks = []
        for assertion_id in group.assertion_ids:
            assertion = plan.assertion(assertion_id)
            item: dict[str, Any] = {
                "assertion_id": assertion_id,
                "text": assertion.source_text,
                "kind": assertion.kind,
                "source_spans": [s.model_dump(mode="json") for s in assertion.spans],
                "status": "pending",
                "result_label": None,
                "explanation": "Check in progress.",
                "source_reports": None,
                "reporting_fidelity": None,
                "medical_interpretation": None,
                "interpretation_limits": [],
                "citations": [],
                "duplicate_of": assertion.duplicate_of,
            }
            if assertion.duplicate_of:
                item.update(
                    status="duplicate",
                    explanation="Repeated statement; see "
                    + assertion.duplicate_of
                    + " for the shared check.",
                )
            elif not assertion.checkable or assertion.planning_status == "not_checkable":
                item.update(
                    status="not_checkable",
                    explanation="Commentary without a separate factual assertion to verify.",
                )
            elif assertion.planning_status != "ready":
                item.update(
                    status="unavailable",
                    result_label="unable_to_verify_reliably",
                    explanation=(
                        "The reference or assertion could not be resolved from the original text."
                    ),
                )
            elif group_runs or (failures or {}).get(group.group_id):
                validated = [
                    r["items"][assertion_id]
                    for r in group_runs
                    if r.get("items", {}).get(assertion_id, {}).get("position") is not None
                ]
                positions = [r["position"] for r in validated]
                label, reason = aggregate_positions(
                    positions, app_env=app_env, risk_class=assertion.risk_class
                )
                if (
                    len(group_runs) < 3
                    and not (failures or {}).get(group.group_id)
                    and label == "unable_to_verify_reliably"
                ):
                    checks.append(item)
                    continue
                item.update(
                    status="unavailable" if label == "unable_to_verify_reliably" else "completed",
                    result_label=label,
                )
                reasons = list(
                    dict.fromkeys(code for r in validated for code in r.get("reason_codes", []))
                )
                checks_with_sources = [
                    c
                    for r in validated
                    for c in r.get("reporting_checks", [])
                    if c.get("source_value")
                ]
                mismatches = list(
                    dict.fromkeys(
                        c["field"].replace("_", " ")
                        for c in checks_with_sources
                        if c["status"] == "mismatch"
                    )
                )
                unresolved = list(
                    dict.fromkeys(
                        c["field"].replace("_", " ")
                        for r in validated
                        for c in r.get("reporting_checks", [])
                        if c["status"] == "unresolved"
                    )
                )
                if label == "unable_to_verify_reliably":
                    explanation = (
                        "Too few independently validated assessments completed this check."
                    )
                elif is_reporting(assertion):
                    explanation = (
                        "The identified study supports this account of what it reported."
                        if label == "supported"
                        else "The identified source differs on "
                        + (", ".join(mismatches) or "one or more reported details")
                        + "."
                        if label == "contradicted"
                        else "The available source does not resolve "
                        + (", ".join(unresolved) or "the study identity or all reported details")
                        + "."
                    )
                else:
                    explanation = {
                        "supported": "Validated evidence supports this medical assertion.",
                        "contradicted": "Validated evidence opposes this medical assertion.",
                        "not_enough_evidence": (
                            "The validated findings do not establish "
                            "this assertion at its stated scope."
                        ),
                    }[label]
                    if reasons:
                        explanation += (
                            " " + ", ".join(c.lower().replace("_", " ") for c in reasons) + "."
                        )
                item["explanation"] = explanation
                assessment = {"result_label": label, "explanation": explanation}
                if is_reporting(assertion):
                    item["reporting_fidelity"] = assessment
                    item["medical_interpretation"] = {
                        "result_label": None,
                        "explanation": (
                            "Accuracy of a study report and a general medical conclusion "
                            "are separate questions. "
                            "A reported association does not by itself establish "
                            "causation or advice."
                        ),
                    }
                else:
                    item["medical_interpretation"] = assessment
                reports = [
                    c["source_value"]
                    for c in checks_with_sources
                    if c["field"] == "reported_result"
                ]
                if reports:
                    item["source_reports"] = reports[0]
                item["interpretation_limits"] = list(
                    dict.fromkeys(
                        limit for r in validated for limit in r.get("interpretation_limits", [])
                    )
                )
                # Display exact validated excerpts where possible, with no model-created quotation.
                used: set[tuple[str, str]] = set()
                for r in validated:
                    quotes = [
                        (unit_id, c["source_value"])
                        for c in r.get("reporting_checks", [])
                        if c.get("source_value") and c["status"] != "unresolved"
                        for unit_id in c["source_unit_ids"]
                    ]
                    if not quotes:
                        quotes = [
                            (uid, units[uid].text)
                            for s in r.get("statements", [])
                            for uid in s["source_unit_ids"]
                            if uid in units
                        ]
                    for uid, quote in quotes:
                        unit = units.get(uid)
                        if unit is None or quote not in unit.text or (uid, quote) in used:
                            continue
                        used.add((uid, quote))
                        doc = docs[unit.document_id]
                        item["citations"].append(
                            {
                                "evidence_id": unit.evidence_id,
                                "source_unit_id": uid,
                                "title": doc.title,
                                "url": doc.canonical_url,
                                "exact_text": quote,
                                "section": unit.section,
                            }
                        )
                item["aggregation_reason"] = reason
                item["qualified_assessments"] = len(validated)
            if item["status"] != "pending":
                completed += 1
            checks.append(item)
        terminal = all(i["status"] != "pending" for i in checks) and (
            len(group_runs) >= 3
            or (failures or {}).get(group.group_id)
            or not any(
                plan.assertion(i).checkable and plan.assertion(i).planning_status == "ready"
                for i in group.assertion_ids
            )
        )
        if terminal:
            groups_completed += 1
        candidates = source_match.get("candidates", [])
        matched = next(
            (
                c
                for c in candidates
                if c.get("document_id") in source_match.get("matched_document_ids", [])
            ),
            None,
        )
        groups.append(
            {
                "group_id": group.group_id,
                "title": group.title,
                "status": "completed" if terminal else "running",
                "source_match": {
                    "status": source_match.get("status", "not_found")
                    if source_match.get("status") != "not_applicable"
                    else "not_found",
                    "title": matched.get("title") if matched else None,
                    "url": matched.get("url", matched.get("canonical_url")) if matched else None,
                    "reason": source_match.get("reason", "Source identification is pending."),
                    "candidates": [
                        {
                            "title": c["title"],
                            "url": c.get("url", c.get("canonical_url")),
                            "reason": c.get("reason", "; ".join(c.get("matching_evidence", []))),
                        }
                        for c in candidates
                    ],
                    "discrepancies": source_match.get("discrepancies", []),
                },
                "assertions": checks,
            }
        )
    return {
        "version": VERSION,
        "analysis_id": str(analysis_id),
        "status": status,
        "production_qualified": False,
        "groups": groups,
        "progress": {
            "groups_total": len(groups),
            "groups_completed": groups_completed,
            "assertions_total": len(plan.assertions),
            "assertions_completed": completed,
        },
    }
