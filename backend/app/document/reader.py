"""Read-only, source-traced reader projection. Never qualify or relabel an item."""

import re
from typing import Any

from app.document.models import DocumentPlan

VERSION = "reader-view-1.0"


def _sentence(
    key: str, text: str, items: list[dict[str, Any]], basis: str = "saved_status"
) -> dict[str, Any]:
    return {
        "id": key,
        "text": text,
        "basis": basis,
        "references": [
            {
                "assertionIds": [a["assertion_id"] for a in items],
                "sourceUnitIds": list(
                    dict.fromkeys(c["source_unit_id"] for a in items for c in a["citations"])
                ),
                "fields": [
                    "status",
                    "result_label",
                    "assessment_target",
                    "explanation",
                    "text",
                    "citations",
                    "field_diagnostics",
                    "reason_codes",
                ],
            }
        ],
    }


def _fields(item: dict[str, Any]) -> set[str]:
    return {d["field"] for d in item.get("field_diagnostics", [])}


def _review(item: dict[str, Any]) -> bool:
    # A display warning only. Neither missing documentation nor this phrase is
    # converted into a finding that no adjustment occurred.
    return "adjustment_set" in _fields(item) and any(
        re.search(r"\bfor each predictor variable\b", c["exact_text"], re.I)
        for c in item["citations"]
    )


def _explanation(item: dict[str, Any], reporting: bool) -> str:
    state, label = item["status"], item["result_label"]
    if _review(item):
        return (
            "The cited methods describe analysis for each predictor variable. This does not "
            "establish that the estimate accounts for all the named factors together. It also "
            "does not prove that no adjustment occurred. The saved result is unchanged."
        )
    if state == "pending":
        return "This part is still being checked. It has no completed result yet."
    if state == "unavailable":
        reason = item.get("failure_kind")
        if reason == "source_not_identified":
            return (
                "The described source could not be securely identified, so this check "
                "remains incomplete."
            )
        if reason in {"unresolved_reference", "normalization_incomplete"}:
            return (
                "The wording or its context could not be resolved reliably. This part "
                "remains unverified."
            )
        return (
            "This check did not receive enough valid assessments to finish. The source context "
            "below is available, but it is not confirmation of the submitted claim."
        )
    reasons = set(item.get("reason_codes", []))
    if "reported_effect_measure_not_comparable" in reasons:
        return (
            "The statistic's meaning was not established as comparable to the claimed change "
            "in risk. A number appearing in the paper does not confirm that interpretation."
        )
    if "adjustment_set" in _fields(item) and label != "supported":
        return (
            "The completed checks did not settle whether all the named factors were accounted "
            "for together in the model producing this estimate. A list of variables alone is "
            "not enough; missing documentation also does not prove no adjustment occurred."
        )
    if "VALIDATED_JUDGE_DISAGREEMENT" in reasons:
        return (
            "The completed evidence checks disagree. This part cannot be treated as an "
            "established conclusion."
        )
    if "CAUSAL_DESIGN_INSUFFICIENT" in reasons:
        return "The available study designs do not establish cause and effect for this claim."
    if label == "not_enough_evidence":
        return (
            "The completed evidence checks do not establish this claim at its stated scope. "
            "This is a scientific limitation, not an interrupted check."
        )
    if reporting:
        return (
            "The completed source checks confirm this detail in the identified paper."
            if label == "supported"
            else "The completed source checks find that this detail does not match the paper."
        )
    return (
        "The validated medical evidence supports the claim at its stated scope."
        if label == "supported"
        else "The validated medical evidence opposes the claim at its stated scope."
    )


def _question(item: dict[str, Any], plan: DocumentPlan) -> str:
    fields = _fields(item)
    assertion = plan.assertion(item["assertion_id"])
    if "adjustment_set" in fields or re.search(
        r"\badjust(?:ed|ment)\b", assertion.source_text, re.I
    ):
        return "Were other risk factors accounted for?"
    if "effect_value" in fields or assertion.pico.numeric_effect:
        return "What does the reported number mean?"
    if assertion.kind == "sample_size" or "sample_size" in fields:
        return "Does the participant count match?"
    if assertion.kind == "methodology":
        return "Does the description of the study methods match?"
    if item.get("assessment_target") == "reporting_fidelity" and re.search(
        r"\b(?:highlights?|patterns?|overall|summary)\b", assertion.source_text, re.I
    ):
        return "Does the broad association summary match?"
    outcome = " ".join((assertion.pico.outcome or "").split())
    if outcome and len(outcome) < 90:
        return f"What did the check establish about {outcome}?"
    return "What did the check establish about this claim?"


def build_reader_view(report: dict[str, Any], plan: DocumentPlan) -> dict[str, Any]:
    """Called only after the saved report/parents pass existing exact audit checks.

    Topic headings are descriptive, not an overall medical verdict. Approved
    descriptions stay separate from failed specific results. No judge prose is
    used to write facts; all positions/IDs/quotations come from the verified report.
    """
    topics = []
    for group in report["groups"]:
        items = [
            a for a in group["assertions"] if a["status"] in {"completed", "unavailable", "pending"}
        ]
        if not items:
            continue
        reporting = all(a.get("assessment_target") == "reporting_fidelity" for a in items)
        targets = {a.get("assessment_target") for a in items}
        scope = (
            "mixed" if len(targets) > 1 else "study_reporting" if reporting else "medical_evidence"
        )
        unavailable = [a for a in items if a["status"] == "unavailable"]
        pending = [a for a in items if a["status"] == "pending"]
        unresolved = [
            a
            for a in items
            if a["status"] == "completed" and a["result_label"] == "not_enough_evidence"
        ]
        mismatches = [
            a for a in items if a["status"] == "completed" and a["result_label"] == "contradicted"
        ]
        matched = [
            a
            for a in items
            if a["status"] == "completed" and a["result_label"] == "supported" and not _review(a)
        ]
        descriptions = [
            a
            for a in matched
            if a.get("assessment_target") == "reporting_fidelity"
            and (
                "sample_size" in _fields(a)
                or plan.assertion(a["assertion_id"]).kind == "sample_size"
                or re.search(r"\b(?:looked at|examined|studied|investigated)\b", a["text"], re.I)
            )
        ]
        review = [a for a in items if _review(a)]
        identified = group["source_match"]["status"] == "identified"
        state = (
            "incomplete"
            if unavailable or pending
            else "inconclusive"
            if unresolved
            else "completed"
        )
        headline = (
            "We found the study, but couldn't finish checking its main claims."
            if reporting and identified and unavailable
            else "We couldn't complete a reliable check of this section."
            if unavailable
            else "This section is still being checked."
            if pending
            else "Important parts of the paragraph remain unresolved."
            if unresolved
            else "Some statements do not match the paper."
            if reporting and mismatches
            else "The medical evidence opposes this claim."
            if mismatches
            else "The paper was found, but a reporting detail needs review."
            if review
            else "The checked details match the paper."
            if reporting
            else "The validated medical evidence supports this claim."
        )
        if scope == "mixed" and not unavailable and not pending:
            headline = "The paragraph needs separate reporting and medical checks."
        elif not reporting and matched and mismatches:
            headline = "The medical checks reached different conclusions."
        established = []
        if descriptions:
            has_size = any(
                "sample_size" in _fields(a)
                or plan.assertion(a["assertion_id"]).kind == "sample_size"
                for a in descriptions
            )
            has_subject = any(
                re.search(r"\b(?:looked at|examined|studied|investigated)\b", a["text"], re.I)
                for a in descriptions
            )
            description = (
                "The study's participant count and subject match the submitted description."
                if has_size and has_subject
                else "The study's participant count matches the submitted description."
                if has_size
                else "The study's subject matches the submitted description."
            )
            established.append(
                _sentence(
                    "description",
                    description,
                    descriptions,
                    "approved_finding",
                )
            )
        if not unavailable and not pending and not unresolved and not review:
            short = next(
                (a for a in matched + mismatches if len(" ".join(a["text"].split())) <= 230), None
            )
            if short:
                established.append(
                    _sentence(
                        "finding",
                        "The checked wording was: “" + " ".join(short["text"].split()) + "”",
                        [short],
                        "saved_assessment",
                    )
                )
        if unavailable or pending:
            unfinished = (
                "The main findings and their interpretation remain unverified wherever a "
                "check could not finish."
            )
            numeric = next(
                (
                    plan.assertion(a["assertion_id"]).pico.numeric_effect
                    for a in unavailable + pending
                    if plan.assertion(a["assertion_id"]).pico.numeric_effect
                ),
                None,
            )
            if numeric and numeric.status == "parsed" and len(numeric.raw_text) <= 70:
                unfinished = (
                    "We did not finish verifying the main findings, including the claimed “"
                    + " ".join(numeric.raw_text.split())
                    + "” effect."
                )
            established.append(
                _sentence(
                    "unfinished",
                    unfinished + " A completed broad description does not confirm a more "
                    "specific unfinished claim.",
                    unavailable + pending,
                )
            )
            if numeric and numeric.status == "parsed" and len(numeric.raw_text) <= 70:
                established[-1]["references"][0]["fields"].append(
                    "plan.assertions.pico.numeric_effect.raw_text"
                )
        elif unresolved:
            established.append(
                _sentence(
                    "unresolved",
                    (
                        "The completed checks did not establish all the stated conclusions. "
                        "Open the evidence to see which details remain unresolved and why."
                    ),
                    unresolved,
                    "saved_assessment",
                )
            )
        elif mismatches:
            established.append(
                _sentence(
                    "mismatch",
                    (
                        "The completed checks identify a mismatch between the submitted wording "
                        "and the evidence. Each distinct claim and endpoint is explained below."
                    ),
                    mismatches,
                    "saved_assessment",
                )
            )
        else:
            established.append(
                _sentence(
                    "completed",
                    (
                        "These checks are complete at the scope described below. The evidence "
                        "explains what was verified and which source passages support it."
                    ),
                    items,
                )
            )
        limits = []
        if review:
            limits.append(
                _sentence(
                    "review",
                    (
                        "The claim about other risk factors also needs review. Its saved result "
                        "has not been changed, and the evidence issue is flagged below."
                    ),
                    review,
                    "correctness_finding",
                )
            )
        if unavailable:
            limits.append(
                _sentence(
                    "operational-limit",
                    (
                        "This is an incomplete check, not evidence that the unfinished claims are "
                        "true or false. Available source passages do not turn an unfinished "
                        "assessment into a completed one."
                    ),
                    unavailable,
                )
            )
        elif unresolved:
            limits.append(
                _sentence(
                    "scientific-limit",
                    (
                        "The uncertainty concerns what the evidence establishes, rather than a "
                        "processing failure. An unresolved result should not be read as "
                        "confirmation of the claim."
                    ),
                    unresolved,
                    "saved_assessment",
                )
            )
        if scope == "mixed":
            limits.append(
                _sentence(
                    "scope",
                    (
                        "This section includes both study reporting and medical claims. A paper's "
                        "reporting and a medical conclusion are separate questions, shown "
                        "individually below."
                    ),
                    items,
                    "scope_limit",
                )
            )
        elif reporting:
            limits.append(
                _sentence(
                    "scope",
                    (
                        "This checks how accurately the paragraph describes a paper. Matching its "
                        "reporting does not, by itself, establish a medical cause, treatment "
                        "benefit or recommendation."
                    ),
                    items,
                    "scope_limit",
                )
            )
        else:
            limits.append(
                _sentence(
                    "scope",
                    (
                        "This concerns the medical claim at its stated population and outcome. "
                        "Results for a different endpoint or a narrower group do not automatically "
                        "answer a broader question."
                    ),
                    items,
                    "scope_limit",
                )
            )
        questions = []
        if reporting and identified and descriptions:
            first = descriptions[0]
            questions.append(
                {
                    "id": "study-description",
                    "question": "Did we find the study described?",
                    "assertionIds": [a["assertion_id"] for a in descriptions],
                    "answer": _sentence(
                        "study-answer", description, descriptions, "approved_finding"
                    ),
                    "explanation": [
                        _sentence(
                            "study-scope",
                            "This confirms the description of the source. Its reported "
                            "effects and their interpretation are separate checks below.",
                            descriptions,
                            "scope_limit",
                        )
                    ],
                    "quotes": [
                        {
                            "assertionId": first["assertion_id"],
                            "sourceUnitId": c["source_unit_id"],
                            "text": c.get("excerpt") or c["exact_text"],
                            "use": "verified_passage",
                        }
                        for c in first["citations"][-1:]
                    ],
                }
            )
        for item in items:
            if reporting and identified and item in descriptions:
                continue
            aid = item["assertion_id"]
            explanation = _explanation(item, item.get("assessment_target") == "reporting_fidelity")
            quotes = [
                {
                    "assertionId": aid,
                    "sourceUnitId": c["source_unit_id"],
                    "text": c.get("excerpt") or c["exact_text"],
                    "use": "correctness_review"
                    if _review(item)
                    else "source_context"
                    if item["status"] in {"pending", "unavailable"}
                    else "verified_passage",
                }
                for c in item["citations"][:1]
            ]
            question = {
                "id": aid,
                "question": _question(item, plan),
                "assertionIds": [aid],
                "answer": _sentence(
                    "answer-" + aid,
                    explanation,
                    [item],
                    "correctness_finding" if _review(item) else "saved_status",
                ),
                "explanation": [
                    _sentence(
                        "wording-" + aid,
                        "Submitted wording: “" + " ".join(item["text"].split()) + "”",
                        [item],
                        "scope_limit",
                    )
                ],
                "quotes": quotes,
            }
            if _review(item):
                question["correctnessFlag"] = "Evidence review flagged · Saved result unchanged"
            questions.append(question)
        topics.append(
            {
                "id": group["group_id"],
                "state": state,
                "scope": scope,
                "headline": _sentence("headline", headline, items),
                "established": established,
                "limitation": limits,
                "questions": questions,
                "selectedAssertionIds": [a["assertion_id"] for a in items],
            }
        )
    return {"version": VERSION, "topics": topics}
