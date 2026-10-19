"""Reader copy is a traced projection, not another evidence decision."""

import json
from copy import deepcopy

from app.document.reader import build_reader_view
from tests.test_document_clarity import parents


def saved(monkeypatch):
    from app.document.report import build_document_report

    identifier, plan, evidence, runs, _ = parents(monkeypatch)
    report = build_document_report(
        identifier, plan, evidence, runs, app_env="test", status="completed"
    )
    return plan, report


def test_reader_does_not_change_a_saved_result_or_use_raw_judge_prose(monkeypatch):
    plan, report = saved(monkeypatch)
    report["debug_group_runs"] = [{"raw_response": "Invented overall verdict: definitely true."}]
    before = deepcopy(report)
    view = build_reader_view(report, plan)
    assert report == before
    assert view["version"] == "reader-view-1.0"
    assert "Invented overall verdict" not in json.dumps(view)
    assert "overall_verdict" not in view
    for topic in view["topics"]:
        for line in [topic["headline"], *topic["established"], *topic["limitation"]]:
            assert line["references"][0]["assertionIds"]
            ref = line["references"][0]
            allowed = {
                c["source_unit_id"]
                for group in report["groups"]
                for item in group["assertions"]
                if item["assertion_id"] in ref["assertionIds"]
                for c in item["citations"]
            }
            assert set(ref["sourceUnitIds"]) == allowed


def test_incomplete_specific_check_is_not_replaced_by_a_supported_broad_statement(monkeypatch):
    plan, report = saved(monkeypatch)
    item = report["groups"][0]["assertions"][1]
    item.update(status="unavailable", result_label="unable_to_verify_reliably")
    view = build_reader_view(report, plan)
    topic = view["topics"][0]
    assert topic["state"] == "incomplete"
    assert "couldn't finish" in topic["headline"]["text"]
    assert any("broad description" in s["text"] for s in topic["established"])
    assert item["result_label"] == "unable_to_verify_reliably"
    assert not any(
        s["basis"] == "approved_finding" and "A2" in s["references"][0]["assertionIds"]
        for s in topic["established"]
    )


def test_nei_remains_a_completed_assessment_not_an_operational_failure(monkeypatch):
    plan, report = saved(monkeypatch)
    item = report["groups"][0]["assertions"][0]
    item.update(result_label="not_enough_evidence")
    item["reason_codes"] = ["reported_effect_measure_not_comparable"]
    topic = build_reader_view(report, plan)["topics"][0]
    assert topic["state"] == "inconclusive"
    assert "statistic" in topic["questions"][0]["answer"]["text"].lower()
    assert item["status"] == "completed"


def test_adjustment_review_flag_is_generic_and_does_not_relabel_the_item(monkeypatch):
    plan, report = saved(monkeypatch)
    item = report["groups"][0]["assertions"][1]
    item["field_diagnostics"] = [{"field": "adjustment_set"}]
    item["citations"][0]["exact_text"] = "The analysis was performed for each predictor variable."
    topic = build_reader_view(report, plan)["topics"][0]
    question = topic["questions"][1]
    assert question["correctnessFlag"]
    assert "does not prove that no adjustment" in question["answer"]["text"]
    assert item["result_label"] == "supported"
    assert any(s["basis"] == "correctness_finding" for s in topic["limitation"])


def test_reader_quotes_are_exact_owned_passages(monkeypatch):
    plan, report = saved(monkeypatch)
    for topic in build_reader_view(report, plan)["topics"]:
        for question in topic["questions"]:
            for quote in question["quotes"]:
                original = next(
                    a
                    for g in report["groups"]
                    for a in g["assertions"]
                    if a["assertion_id"] == quote["assertionId"]
                )
                citation = next(
                    c for c in original["citations"] if c["source_unit_id"] == quote["sourceUnitId"]
                )
                assert quote["text"] in citation["exact_text"]


def test_mixed_reporting_and_medical_items_have_separate_scope_not_a_document_verdict(monkeypatch):
    plan, report = saved(monkeypatch)
    report["groups"][0]["assertions"][1]["assessment_target"] = "medical_evidence"
    topic = build_reader_view(report, plan)["topics"][0]
    assert topic["scope"] == "mixed"
    assert "separate" in topic["headline"]["text"]
    assert "position" not in topic and "result_label" not in topic


def test_unfinished_numeric_wording_uses_the_existing_structured_claim_and_traces_it(monkeypatch):
    from app.pipeline.numeric_effect import numeric_effect

    plan, report = saved(monkeypatch)
    item = report["groups"][0]["assertions"][1]
    item.update(status="unavailable", result_label="unable_to_verify_reliably")
    assertion = plan.assertion(item["assertion_id"])
    changed = assertion.model_copy(
        update={
            "pico": assertion.pico.model_copy(
                update={
                    "numeric_effect": numeric_effect("up to a 37% increased risk"),
                }
            )
        }
    )
    plan = plan.model_copy(
        update={
            "assertions": tuple(
                changed if a.assertion_id == changed.assertion_id else a for a in plan.assertions
            )
        }
    )
    topic = build_reader_view(report, plan)["topics"][0]
    wording = next(s for s in topic["established"] if s["id"] == "unfinished")
    assert "claimed" in wording["text"] and "37%" in wording["text"]
    assert "plan.assertions.pico.numeric_effect.raw_text" in wording["references"][0]["fields"]
    assert wording["basis"] == "saved_status"
    assert item["result_label"] == "unable_to_verify_reliably"
