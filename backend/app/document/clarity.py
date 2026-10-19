"Controlled, traceable reading view. No model calls, new votes or numeric conversions."

import re
from collections import Counter
from copy import deepcopy
from typing import Any

from app.document.evaluation import is_reporting, reporting_fields
from app.document.models import DocumentAssertion, DocumentPlan

REPORTING_LABELS = {
    "supported": "Matches the paper",
    "contradicted": "Does not match the paper",
    "not_enough_evidence": "Could not verify this detail",
    "unable_to_verify_reliably": "Check unavailable",
}
FIELD_NAMES = {
    "study_identity": "study identity",
    "reported_result": "reported finding",
    "population": "population",
    "exposure": "exposure",
    "endpoint": "outcome",
    "effect_measure": "statistical measure",
    "effect_value": "effect size",
    "comparison": "comparison group",
    "qualifiers": "qualifiers",
    "adjustment_set": "adjusted variables",
    "sample_size": "participant count",
}


def status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    """Disjoint states: processing completion is not evidence verification."""
    counts = Counter(item["status"] for item in items)
    return {
        "total": len(items),
        "assessed": counts["completed"],
        "unavailable": counts["unavailable"],
        "background": counts["not_checkable"] + counts["duplicate"],
        "pending": counts["pending"],
        "processed": len(items) - counts["pending"],
    }


def short_heading(assertion: DocumentAssertion, fields: set[str]) -> str:
    if assertion.duplicate_of:
        return "Repeated wording"
    if not assertion.checkable:
        return (
            "Source note"
            if re.match(r"\s*source\s*:", assertion.source_text, re.I)
            else "Background wording"
        )
    if assertion.kind == "sample_size":
        return "Participant count"
    if "adjustment_set" in fields:
        return "Adjusted variables"
    if "effect_value" in fields or assertion.pico.numeric_effect is not None:
        return "Reported effect size"
    outcome = " ".join((assertion.pico.outcome or "").split())
    if assertion.kind == "interpretation":
        return "Interpretation of the findings"
    if outcome:
        return ("Reported finding: " if is_reporting(assertion) else "Medical claim: ") + outcome
    return (
        "Study methods"
        if assertion.kind == "methodology"
        else "Reported finding"
        if is_reporting(assertion)
        else "Medical claim"
    )


def _field_diagnostics(validated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields: dict[str, list[dict[str, Any]]] = {}
    for run in validated:
        for check in run.get("reporting_checks", []):
            fields.setdefault(check["field"], []).append(check)
    return [
        {
            "field": field,
            "statuses": list(dict.fromkeys(c["status"] for c in checks)),
            "source_unit_ids": list(dict.fromkeys(u for c in checks for u in c["source_unit_ids"])),
            "source_quantity_ids": list(
                dict.fromkeys(q for c in checks for q in c["source_quantity_ids"])
            ),
        }
        for field, checks in fields.items()
    ]


def _numeric_detail(validated: list[dict[str, Any]], saved: dict[str, Any]) -> dict[str, Any]:
    units = {u["unit_id"]: u for u in saved.get("source_units", [])}
    catalog = {
        q["quantity_id"]: q for q in saved.get("source_quantity_catalog", {}).get("items", [])
    }
    ids = list(
        dict.fromkeys(
            q
            for r in validated
            for c in r.get("reporting_checks", [])
            if c["field"] == "effect_value"
            for q in c["source_quantity_ids"]
        )
    )
    selected = [catalog[q] for q in ids if q in catalog]
    # Read frozen source context, never a judge's numeric paraphrase. This only
    # explains uncertainty; it does not retag catalog quantities or qualify them.
    referenced = {
        u for r in validated for c in r.get("reporting_checks", []) for u in c["source_unit_ids"]
    }
    methods = [
        u
        for uid, u in units.items()
        if uid in referenced
        and re.search(r"multinomial logistic regression", u["text"], re.I)
        and re.search(r"log\s*\(\s*odds ratios\s*\)", u["text"], re.I)
    ]
    return {
        "quantities": selected,
        "method_source_unit_ids": [u["unit_id"] for u in methods],
        "method": "multinomial_logistic" if methods else None,
        "conversion_status": "not_established",
    }


def _explanation(
    item: dict[str, Any],
    reporting: bool,
    diagnostics: list[dict[str, Any]],
    numeric: dict[str, Any],
) -> str:
    state, label = item["status"], item["result_label"]
    if state == "pending":
        return "This detail is still being checked."
    if state == "not_checkable":
        return (
            "This wording was retained as background, not independently assessed."
            " Comparative or interpretive wording here has not been verified."
        )
    if state == "duplicate":
        return (
            "This repeats earlier wording. Its original text is retained; it does"
            " not add an independent assessment."
        )
    if state == "unavailable":
        if item.get("failure_kind") == "unresolved_reference":
            return (
                "The reference connecting this detail to its study or finding could not be "
                "resolved from the submitted text. This detail remains unverified; "
                "the study may still have been identified for other checks."
            )
        if item.get("failure_kind") == "source_not_identified":
            return (
                "The described source could not be securely identified, so no qualified "
                "assessment of this reporting detail was completed. This does not establish "
                "that the opposite is true."
            )
        if item.get("failure_kind") == "processing_failed":
            return (
                "Processing this section failed before an assessment could be "
                "completed. This is not evidence for or against the submitted "
                "wording."
            )
        if item.get("failure_kind") == "normalization_incomplete":
            return (
                "The text does not provide a complete, grounded question for this "
                "check. No medical conclusion was reached; missing context is not "
                "contrary evidence."
            )
        prefix = (
            "Too few independently validated assessments completed this check. "
            "This is a processing limitation, not a finding that the claim is "
            "false."
        )
        return prefix + (" " + str(item["partial_detail"]) if item.get("partial_detail") else "")
    if not reporting:
        return str(item["explanation"])
    reasons = set(item["reason_codes"])
    if "reported_effect_measure_not_comparable" in reasons:
        literals = list(dict.fromkeys(q["literal"] for q in numeric["quantities"]))
        present = (
            "The cited source contains " + ", ".join(literals) + ". "
            if literals
            else "The source contains a numeric result, but its interpretation is unresolved. "
        )
        method = (
            (
                "The frozen methods describe multinomial logistic regression and "
                "exponentiated log-odds. These category-relative estimates must not "
                "be treated as ordinary disease risk ratios. "
                "They compare disease categories with a reference category, rather "
                "than directly measuring a person's chance of developing the disease. "
            )
            if numeric["method"]
            else (
                "The selected statistical measure is not established as comparable to"
                " the claim in the frozen quantity metadata. "
            )
        )
        return (
            present
            + method
            + (
                "A percent increase calculated from a ratio alone does not establish "
                "the same percent increase in disease probability. The claimed "
                "conversion remains unverified."
            )
        )
    adjustment = next((d for d in diagnostics if d["field"] == "adjustment_set"), None)
    if adjustment and label != "supported":
        prefix = (
            (
                "Independently validated checks disagree about whether the claimed "
                "adjustment set matches the paper. "
            )
            if item["aggregation_reason"] == "VALIDATED_JUDGE_DISAGREEMENT"
            else "The claimed adjustment set could not be confirmed. "
            if label == "not_enough_evidence"
            else "The validated checks find a mismatch in the claimed adjustment set. "
        )
        return prefix + (
            "Variables mentioned or analyzed separately do not show that all were"
            " adjusted for together in the model behind this estimate. This does "
            "not establish definite non-adjustment from incomplete documentation."
        )
    if item["aggregation_reason"] == "VALIDATED_JUDGE_DISAGREEMENT":
        return (
            "Independently validated assessments disagree about this reported "
            "detail. The disagreement remains unresolved; neither account is "
            "presented as an established fact."
        )
    unresolved = [
        FIELD_NAMES.get(d["field"], d["field"].replace("_", " "))
        for d in diagnostics
        if "unresolved" in d["statuses"]
    ]
    mismatches = [
        FIELD_NAMES.get(d["field"], d["field"].replace("_", " "))
        for d in diagnostics
        if "mismatch" in d["statuses"]
    ]
    if label == "supported":
        return (
            "Independently validated checks confirm this detail in the identified"
            " paper. This result concerns the accuracy of the reporting."
        )
    if label == "contradicted":
        return (
            "The validated source check finds a mismatch in "
            + (", ".join(mismatches) or "the reported detail")
            + (
                ". This concerns what the paper reports, rather than the truth of a "
                "broader medical claim."
            )
        )
    if "reported_source_identity_uncertain" in reasons:
        return (
            "The search did not securely identify the particular study being "
            "described, so this detail cannot be verified against that study."
        )
    numeric_reasons = {
        "reported_effect_value_not_comparable": (
            "The selected source quantity does not establish the stated numeric value."
        ),
        "reported_effect_bound_not_established": (
            "The source does not establish the stated numeric range or limit."
        ),
        "reported_source_bound_not_exact_value": (
            "The source gives a bound or range, which cannot verify an exact point estimate."
        ),
        "reported_effect_direction_not_comparable": (
            "The stated effect direction and selected source quantity are not comparable."
        ),
    }
    for code, text in numeric_reasons.items():
        if code in reasons:
            return (
                text + " The study may be identified while this numeric detail remains unresolved."
            )
    return (
        "The validated source checks do not resolve "
        + (", ".join(unresolved) or "this reported detail")
        + (
            ". This is a limitation of this detail, not proof that the study is "
            "missing or the opposite is true."
        )
    )


def _excerpt(text: str, focus: list[str], *, table: bool = False) -> tuple[str, int, int]:
    # Keep full sentences, negation and qualifiers. Never abbreviate a table row
    # away from its headings/footnotes. The full original remains accessible once.
    if table:
        return text, 0, len(text)
    boundaries = [
        0,
        *[m.end() for m in re.finditer(r"[.!?](?:[\"”’')\]]*)\s+(?=[A-Z])", text)],
        len(text),
    ]
    spans = [
        (a, b) for a, b in zip(boundaries[:-1], boundaries[1:], strict=True) if text[a:b].strip()
    ]
    if not spans:
        return text, 0, len(text)
    index = max(
        range(len(spans)),
        key=lambda i: sum(
            (100 if re.fullmatch(r"\d+(?:\.\d+)?", word) else 1)
            for word in focus
            if word.lower() in text[spans[i][0] : spans[i][1]].lower()
        ),
    )
    start, end = spans[index]
    if end - start < 180 and index + 1 < len(spans):
        end = spans[index + 1][1]
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return text[start:end], start, end


def _source_state(
    group: dict[str, Any], saved: dict[str, Any], failure: str | None, plan: DocumentPlan
) -> None:
    source = group["source_match"]
    applicable = bool(plan.group(group["group_id"]).study_clues)
    if not saved:
        if failure:
            source.update(
                status="failed",
                search_state="failed",
                reason="Source search could not be completed for this section.",
            )
        elif not applicable or not any(a["status"] == "pending" for a in group["assertions"]):
            source.update(
                status="not_applicable",
                search_state="not_applicable",
                reason="No independently checkable study reference is available for this section.",
            )
        else:
            source.update(status="pending", search_state="pending")
    else:
        raw_status = saved["source_match"]["status"]
        failed_search = any(
            "search unavailable" in limit.lower() for limit in saved.get("limitations", [])
        )
        no_queries = not saved.get("query_executions") and not saved.get("fulltext_sources")
        source.update(
            status=raw_status,
            search_state="not_applicable" if raw_status == "not_applicable" else "searched",
        )
        if raw_status == "not_found" and failed_search:
            source.update(
                status="failed",
                search_state="failed",
                reason="Source search failed; it did not establish that the source was absent.",
            )
        elif no_queries and raw_status == "not_found":
            source.update(
                status="not_applicable",
                search_state="not_applicable",
                reason="A grounded source-search question could not be formed.",
            )
    group["processing_status"] = (
        "failed" if failure else "finished" if group["status"] == "completed" else "running"
    )


def _attachment_group(plan: DocumentPlan, aid: str) -> str | None:
    assertion = plan.assertion(aid)
    if assertion.checkable and assertion.kind != "interpretation":
        return None
    owner = next(g for g in plan.groups if aid in g.assertion_ids)
    if re.match(r"\s*source\s*:", assertion.source_text, re.I):
        hosts = [
            g.group_id
            for g in plan.groups
            if g.group_id != owner.group_id
            and any(
                s.start <= span.start and span.end <= s.end
                for s in g.study_clues
                for span in assertion.spans
            )
        ]
        if len(hosts) == 1:
            return hosts[0]
    # Only explicit literal links or the planner's study ownership join topics;
    # unnamed experts with no such link remain independently visible.
    linked = [
        link.target
        for link in plan.context_links
        if link.link_id in assertion.context_link_ids and link.resolved
    ]
    hosts = [
        g.group_id
        for g in plan.groups
        if g.group_id != owner.group_id
        and (
            assertion.study_id is not None
            and assertion.study_id == g.study_id
            or any(
                target
                and any(
                    s.start <= target.start and target.end <= s.end
                    for i in g.assertion_ids
                    for s in plan.assertion(i).spans
                )
                for target in linked
            )
        )
    ]
    return hosts[0] if len(hosts) == 1 else None


def _trace(text: str, pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    return {
        "text": text,
        "assertion_ids": [a["assertion_id"] for _, a in pairs],
        "group_ids": list(dict.fromkeys(g["group_id"] for g, _ in pairs)),
        "evidence": [
            {
                "assertion_id": a["assertion_id"],
                "group_id": g["group_id"],
                "source_unit_ids": list(dict.fromkeys(c["source_unit_id"] for c in a["citations"])),
            }
            for g, a in pairs
            if a["status"] == "completed"
        ],
    }


def clarify_report(
    legacy: dict[str, Any],
    plan: DocumentPlan,
    evidence: dict[str, dict[str, Any]],
    runs: dict[str, list[dict[str, Any]]],
    failures: dict[str, str],
    *,
    version: str = "document-report-1.3",
) -> dict[str, Any]:
    report = deepcopy(legacy)
    report["version"] = version
    all_pairs = []
    for group in report["groups"]:
        gid = group["group_id"]
        saved = evidence.get(gid, {})
        group["sources"] = []
        seen_sources: set[str] = set()
        for item in group["assertions"]:
            aid = item["assertion_id"]
            assertion = plan.assertion(aid)
            validated = [
                r["items"][aid]
                for r in runs.get(gid, [])
                if r.get("items", {}).get(aid, {}).get("position") is not None
            ]
            diagnostics = _field_diagnostics(validated)
            numeric = _numeric_detail(validated, saved)
            item["reason_codes"] = list(
                dict.fromkeys(code for r in validated for code in r.get("reason_codes", []))
            )
            item["field_diagnostics"] = diagnostics
            item["numeric_detail"] = numeric if numeric["quantities"] else None
            fields = {d["field"] for d in diagnostics}
            if is_reporting(assertion):
                fields.update(reporting_fields(assertion))
            item["heading"] = short_heading(assertion, fields)
            item["assessment_target"] = (
                "reporting_fidelity" if is_reporting(assertion) else "medical_evidence"
            )
            item["failure_kind"] = (
                (
                    "processing_failed"
                    if failures.get(gid)
                    else "unresolved_reference"
                    if assertion.planning_status != "ready"
                    else "normalization_incomplete"
                    if saved.get("normalization_ready", {}).get(aid) is False
                    else "source_not_identified"
                    if is_reporting(assertion)
                    and saved
                    and saved["source_match"]["status"]
                    in {"not_found", "uncertain", "not_applicable"}
                    else "insufficient_validated_assessments"
                )
                if item["status"] == "unavailable"
                else None
            )
            item["aggregation_reason"] = item.get("aggregation_reason", "")
            item["partial_detail"] = None
            if item["status"] == "unavailable" and validated and item["reason_codes"]:
                partial = {**item, "status": "completed", "result_label": "not_enough_evidence"}
                if any(r["position"] == "not_enough_evidence" for r in validated):
                    item["partial_detail"] = (
                        "Individually validated findings flag a limitation, without a completed "
                        "group assessment: "
                        + _explanation(partial, is_reporting(assertion), diagnostics, numeric)
                    )
            item["explanation"] = _explanation(item, is_reporting(assertion), diagnostics, numeric)
            if item.get("reporting_fidelity"):
                item["reporting_fidelity"]["explanation"] = item["explanation"]
            elif item.get("medical_interpretation"):
                item["medical_interpretation"]["explanation"] = item["explanation"]
            association = is_reporting(assertion) and bool(
                re.search(
                    r"\b(?:association|associated|risk|rates|correlated)\b",
                    assertion.source_text,
                    re.I,
                )
            )
            item["association_caveat"] = (
                "An accurately reported association does not by itself establish causation."
                if association and item["status"] == "completed"
                else None
            )
            if is_reporting(assertion):
                item["medical_interpretation"] = None  # reporting did not assess a clinical verdict
                item["interpretation_limits"] = (
                    [item["association_caveat"]] if item["association_caveat"] else []
                )
            item["display_parent_group_id"] = _attachment_group(plan, aid)
            for citation in item["citations"]:
                focus = [
                    q["literal"]
                    for q in numeric["quantities"]
                    if q["source_unit_id"] == citation["source_unit_id"]
                ]
                focus += re.findall(r"[\w-]{5,}", assertion.source_text)
                excerpt, start, end = _excerpt(
                    citation["exact_text"], focus, table="table" in citation["section"].lower()
                )
                citation.update(excerpt=excerpt, excerpt_start=start, excerpt_end=end)
                if citation["source_unit_id"] not in seen_sources:
                    seen_sources.add(citation["source_unit_id"])
                    group["sources"].append(deepcopy(citation))
            all_pairs.append((group, item))
        group["counts"] = status_counts(group["assertions"])
        _source_state(group, saved, failures.get(gid), plan)
        parents = {a["display_parent_group_id"] for a in group["assertions"]}
        group["display_parent_group_id"] = (
            next(iter(parents)) if len(parents) == 1 and None not in parents else None
        )
    counts = status_counts([a for _, a in all_pairs])
    report["progress"].update(counts, assertions_completed=counts["assessed"])
    terminal = report["status"] in {"completed", "partially_completed", "failed"}
    report["completion_text"] = (
        "Finished with limitations"
        if terminal
        and (
            counts["unavailable"]
            or any(a["result_label"] == "not_enough_evidence" for _, a in all_pairs)
        )
        else "Processing finished"
        if terminal
        else "Checks in progress"
    )
    matches = [
        (g, a)
        for g, a in all_pairs
        if a["status"] == "completed" and a["result_label"] == "supported"
    ]
    attention = sorted(
        [
            (g, a)
            for g, a in all_pairs
            if a["status"] == "unavailable"
            or a["status"] == "completed"
            and a["result_label"] != "supported"
        ],
        key=lambda p: (p[1]["status"] == "unavailable", p[1]["result_label"] != "contradicted"),
    )
    reporting_matches = [
        (g, a) for g, a in matches if a["assessment_target"] == "reporting_fidelity"
    ]
    sentences = []
    if reporting_matches:
        topics = list(dict.fromkeys(g["title"] for g, _ in reporting_matches))
        sentences.append(
            _trace(
                f"For {('; '.join(topics))}, "
                f"{len(reporting_matches)} reported details match the identified paper.",
                reporting_matches,
            )
        )
    elif matches:
        sentences.append(
            _trace(
                f"Validated medical evidence supports {len(matches)} of the assessed statements: "
                + "; ".join(a["heading"] for _, a in matches)
                + ".",
                matches,
            )
        )
    else:
        sentences.append(
            _trace("No statement has a qualified matching or supporting result yet.", [])
        )
    unresolved = [(g, a) for g, a in attention if a["status"] == "completed"]
    if unresolved:
        sentences.append(
            _trace(
                "Details needing attention include "
                + "; ".join(a["heading"].lower() for _, a in unresolved)
                + "; their specific limitations are shown below.",
                unresolved,
            )
        )
    if counts["unavailable"] or counts["background"]:
        unavailable = [(g, a) for g, a in all_pairs if a["status"] == "unavailable"]
        sentences.append(
            _trace(
                (
                    f"Checks for {'; '.join(a['heading'].lower() for _, a in unavailable)} "
                    + (
                        "could not be completed. "
                        if version == "document-report-1.2"
                        else "could not be completed; "
                    )
                    if unavailable
                    else ""
                )
                + f"{counts['background']} background or repeated items were "
                "retained without an independent assessment.",
                unavailable,
            )
        )
    elif len(sentences) < 2:
        sentences.append(
            _trace(
                (
                    "Study reporting and medical conclusions remain separate; these "
                    "results are not an overall truth score."
                ),
                [],
            )
        )
    report["reading_summary"] = {
        "main_takeaway": sentences,
        "attention": [
            _trace(a["heading"], [(g, a)])
            | {
                "result_label": a["result_label"],
                "status": a["status"],
                "explanation": a["explanation"],
            }
            for g, a in attention
        ],
        "matches": [
            _trace(a["heading"], [(g, a)]) | {"assessment_target": a["assessment_target"]}
            for g, a in matches
        ],
        "limits": [
            _trace(
                limit,
                [
                    (g, a)
                    for g, a in all_pairs
                    if a["status"] == "completed" and limit in a["interpretation_limits"]
                ],
            )
            for limit in dict.fromkeys(
                limit
                for _, a in all_pairs
                if a["status"] == "completed"
                for limit in a["interpretation_limits"]
            )
        ],
    }
    return report
