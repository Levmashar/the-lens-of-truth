"""Reading-view correctness without another provider, verdict or historical mutation."""

from copy import deepcopy

import pytest

from app.document.clarity import _excerpt, status_counts
from app.document.models import DocumentGroup
from app.document.report import build_document_report
from tests.test_document_audit import fixture


def parents(monkeypatch):
    identifier, report, plan_row, evidence_rows, judge_rows = fixture(monkeypatch)
    from app.document.models import DocumentPlan

    return (
        identifier,
        DocumentPlan.model_validate(plan_row.snapshot_json),
        {r.group_id: r.snapshot_json for r in evidence_rows},
        {"G1": [r.snapshot_json for r in judge_rows]},
        report,
    )


def test_counts_are_disjoint_and_nei_is_assessed():
    values = ["completed", "completed", "unavailable", "not_checkable", "duplicate", "pending"]
    counts = status_counts([{"status": value} for value in values])
    assert counts == {
        "total": 6,
        "assessed": 2,
        "unavailable": 1,
        "background": 2,
        "pending": 1,
        "processed": 5,
    }
    assert sum(counts[k] for k in ("assessed", "unavailable", "background", "pending")) == 6


def test_summary_uses_only_qualified_findings_not_failed_or_pending_proposals(monkeypatch):
    identifier, plan, evidence, runs, _ = parents(monkeypatch)
    for run in runs["G1"]:
        run["items"]["A2"] = {"position": None, "failure": "validator_timeout"}
    report = build_document_report(
        identifier, plan, evidence, runs, app_env="test", status="partially_completed"
    )
    assert report["progress"]["assessed"] == 1
    assert report["progress"]["unavailable"] == 1
    assert report["completion_text"] == "Finished with limitations"
    assert report["reading_summary"]["matches"][0]["assertion_ids"] == ["A1"]
    assert report["reading_summary"]["main_takeaway"][0]["assertion_ids"] == ["A1"]
    assert all(line["evidence"] for line in report["reading_summary"]["matches"])
    assert report["reading_summary"]["attention"][0]["status"] == "unavailable"
    assert "processing limitation" in report["reading_summary"]["attention"][0]["explanation"]


def test_adjustment_disagreement_is_not_a_definite_non_adjustment_fact(monkeypatch):
    identifier, plan, evidence, runs, _ = parents(monkeypatch)
    for i, run in enumerate(runs["G1"]):
        item = run["items"]["A1"]
        item["position"] = "supported" if i == 0 else "contradicted"
        item["reason_codes"] = [
            "accurate_account_of_identified_study" if i == 0 else "reported_adjustment_set_mismatch"
        ]
        item["reporting_checks"].append(
            {
                "field": "adjustment_set",
                "status": "matches" if i == 0 else "mismatch",
                "source_unit_ids": ["E1.U1"],
                "source_quantity_ids": [],
                "source_value": None,
                "reason": "Do not promote this rationale to fact.",
            }
        )
    report = build_document_report(
        identifier, plan, evidence, runs, app_env="test", status="completed"
    )
    item = report["groups"][0]["assertions"][0]
    assert item["result_label"] == "not_enough_evidence"
    assert item["heading"] == "Adjusted variables"
    assert "disagree" in item["explanation"]
    assert "analyzed separately" in item["explanation"]
    assert "does not establish definite non-adjustment" in item["explanation"]
    assert "Do not promote" not in item["explanation"]
    assert item["field_diagnostics"][-1]["statuses"] == ["matches", "mismatch"]


def test_numeric_uncertainty_uses_owned_frozen_quantities_never_judge_numbers(monkeypatch):
    identifier, plan, evidence, runs, _ = parents(monkeypatch)
    saved = evidence["G1"]
    unit = saved["source_units"][0]
    unit["text"] = (
        "Using multinomial logistic regression, the log(odds ratios) were exponentiated. "
        "The category ratio was 3.92."
    )
    quantity = {
        "quantity_id": "E1.U1.Q1",
        "source_unit_id": "E1.U1",
        "literal": "3.92",
        "measure": "unknown",
        "normalization_reason": "unbound_source_numeral_no_conversion",
    }
    saved["source_quantity_catalog"] = {"items": [quantity]}
    for run in runs["G1"]:
        item = run["items"]["A1"]
        item["position"] = "not_enough_evidence"
        item["reason_codes"] = ["reported_effect_measure_not_comparable"]
        item["reporting_checks"].append(
            {
                "field": "effect_value",
                "status": "matches",
                "source_unit_ids": [unit["unit_id"]],
                "source_quantity_ids": ["E1.U1.Q1"],
                "source_value": None,
                "reason": "The judge says the number is 999.9% and definitely causation.",
            }
        )
    report = build_document_report(
        identifier, plan, evidence, runs, app_env="test", status="completed"
    )
    item = report["groups"][0]["assertions"][0]
    assert "contains 3.92" in item["explanation"]
    assert "multinomial logistic regression" in item["explanation"]
    assert "disease probability" in item["explanation"]
    assert "999.9" not in item["explanation"]
    assert item["numeric_detail"]["conversion_status"] == "not_established"
    assert item["result_label"] == "not_enough_evidence"


@pytest.mark.parametrize("case", ["failed", "not_found", "pending", "not_applicable"])
def test_failed_search_is_not_source_not_found(monkeypatch, case):
    identifier, plan, evidence, runs, _ = parents(monkeypatch)
    failures = {}
    if case != "not_found":
        evidence = {}
        runs = {}
    if case == "failed":
        failures = {"G1": "ValueError"}
    elif case == "pending":
        plan = plan.model_copy(
            update={
                "groups": (
                    plan.groups[0].model_copy(
                        update={"study_clues": (plan.assertions[0].spans[0],)}
                    ),
                )
            }
        )
    elif case == "not_found":
        evidence["G1"]["source_match"]["status"] = "not_found"
        evidence["G1"]["query_executions"] = [{"query_id": "Q1", "pmids": []}]
    elif case == "not_applicable":
        plan = plan.model_copy(
            update={
                "groups": (
                    DocumentGroup(
                        group_id="G1",
                        title="Context only",
                        assertion_ids=("A1", "A2"),
                    ),
                )
            }
        )
    report = build_document_report(
        identifier, plan, evidence, runs, app_env="test", status="running", failures=failures
    )
    assert report["groups"][0]["source_match"]["status"] == case


def test_search_exception_recorded_in_evidence_is_still_a_failure(monkeypatch):
    identifier, plan, evidence, runs, _ = parents(monkeypatch)
    evidence["G1"]["source_match"]["status"] = "not_found"
    evidence["G1"]["limitations"] = ["Q1: public source search unavailable (timeout)."]
    report = build_document_report(
        identifier, plan, evidence, runs, app_env="test", status="completed"
    )
    assert report["groups"][0]["source_match"]["status"] == "failed"


def test_legacy_projection_remains_exact_and_upgrade_does_not_mutate_parents(monkeypatch):
    identifier, plan, evidence, runs, _ = parents(monkeypatch)
    before = deepcopy((evidence, runs))
    historical = build_document_report(
        identifier,
        plan,
        evidence,
        runs,
        app_env="test",
        status="completed",
        version="document-report-1.0",
    )
    assert historical["version"] == "document-report-1.0"
    current = build_document_report(
        identifier, plan, evidence, runs, app_env="test", status="completed"
    )
    assert current["version"] == "document-report-1.3"
    assert (evidence, runs) == before
    assert [a["result_label"] for a in current["groups"][0]["assertions"]] == [
        a["result_label"] for a in historical["groups"][0]["assertions"]
    ]
    assert "reading_summary" not in historical


def test_excerpts_keep_whole_negated_qualified_sentences_and_table_context():
    text = (
        "The population was selected. No significant benefit was found in adults with severe "
        "disease. The children were studied separately."
    )
    excerpt, start, end = _excerpt(text, ["benefit"])
    assert text[start:end] == excerpt
    assert "No significant benefit" in excerpt and "severe disease" in excerpt
    table = "Table 2. Outcome: melanoma. Group: adults. RR=3.92. Footnote: unadjusted."
    assert _excerpt(table, ["3.92"], table=True) == (table, 0, len(table))


def test_takeaway_stays_three_sentences_and_retains_the_previous_reading_version(monkeypatch):
    identifier, plan, evidence, runs, _ = parents(monkeypatch)
    for run in runs["G1"]:
        run["items"]["A2"] = {"position": None, "failure": "validator_timeout"}
    arguments = {"app_env": "test", "status": "partially_completed"}
    previous = build_document_report(
        identifier, plan, evidence, runs, **arguments, version="document-report-1.2"
    )
    frozen = deepcopy(previous)
    current = build_document_report(identifier, plan, evidence, runs, **arguments)
    text = " ".join(line["text"] for line in current["reading_summary"]["main_takeaway"])
    assert 2 <= text.count(".") <= 3
    assert "could not be completed;" in text
    assert previous == frozen
    assert "could not be completed. " in previous["reading_summary"]["main_takeaway"][-1]["text"]
    assert current["groups"] == previous["groups"]
