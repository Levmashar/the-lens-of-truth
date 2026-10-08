"""Read-time grouped audit replay never calls models and rejects changed parents."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.document import audit, evaluation
from app.document.models import canonical_document_hash
from app.document.report import build_document_report
from app.document.retrieval import (
    GroupEvidenceSnapshot,
    _snapshot_digest,
    document_claim_snapshots,
    document_normalization_audit,
)
from tests.test_document_evaluation import fake_transport, pack, plan, settings


def artifact(analysis_id, kind, data, group_id=None, slot=None):
    return SimpleNamespace(
        analysis_id=analysis_id,
        kind=kind,
        version=data["version"],
        snapshot_json=json.loads(json.dumps(data)),
        snapshot_hash=canonical_document_hash(data),
        group_id=group_id,
        slot=slot,
        created_at=datetime(2026, 10, 7, tzinfo=UTC),
    )


def fixture(monkeypatch, *, failed_slot=None, mutate_judge=None, mutate_validation=None):
    analysis_id = uuid4()
    document = plan(
        (
            "The study reported sunscreen associated with melanoma.",
            "The same study reported an observational association.",
        )
    )
    document = document.model_copy(
        update={
            "assertions": tuple(
                a.model_copy(update={"risk_class": "standard"}) for a in document.assertions
            )
        }
    )
    group = document.groups[0]
    evidence_pack = pack()
    claims = document_claim_snapshots(analysis_id, document, group)
    statuses, qualities, ready = document_normalization_audit(document, group, claims)
    shared = evaluation.document_snapshot(uuid4(), evidence_pack)
    evidence_data = {
        "version": "document-evidence-1.0",
        "group_id": "G1",
        "document_sha256": document.original_sha256,
        "pack": evidence_pack.model_dump(mode="json"),
        "claim_snapshots": {aid: c.model_dump(mode="json") for aid, c in claims.items()},
        "normalization_status": statuses,
        "normalization_quality": {aid: q.model_dump(mode="json") for aid, q in qualities.items()},
        "normalization_ready": ready,
        "per_assertion_evidence_ids": {
            aid: list(evidence_pack.selected_evidence_ids) for aid in claims
        },
        "source_match": {
            "status": "identified",
            "matched_document_ids": ["pubmed:123"],
            "reason": "The frozen cohort matches.",
            "candidates": [],
            "discrepancies": [],
        },
        "source_units": shared["source_units"],
        "source_quantity_catalog": shared["source_quantity_catalog"],
        "source_fetches": {},
        "metrics": {},
        "query_executions": [],
        "candidate_pmids": [],
        "unfetched_candidate_pmids": [],
        "retrieved_passages": [],
        "fulltext_sources": [],
        "source_http_requests": {},
        "limitations": [],
    }
    evidence = GroupEvidenceSnapshot.model_validate(
        {**evidence_data, "snapshot_hash": _snapshot_digest(evidence_data)}
    )
    monkeypatch.setattr(
        evaluation,
        "complete_group",
        fake_transport(
            failed_slot=failed_slot, mutate_judge=mutate_judge, mutate_validation=mutate_validation
        ),
    )
    runs = asyncio.run(
        evaluation.evaluate_group(
            document,
            group,
            evidence.pack,
            evidence.source_match.model_dump(mode="json"),
            analysis_id,
            settings(),
            claim_snapshots=evidence.claim_snapshots,
            per_assertion_evidence_ids=evidence.per_assertion_evidence_ids,
            normalization_ready=evidence.normalization_ready,
        )
    )
    assert all(
        r["items"]["A1"]["position"] == "supported" for r in runs if r["slot"] != failed_slot
    ), runs
    report = build_document_report(
        analysis_id,
        document,
        {"G1": evidence.model_dump(mode="json")},
        {"G1": runs},
        app_env="test",
        status="completed",
    )
    rows = [
        artifact(
            analysis_id,
            "group_judge",
            {
                "version": "document-judge-audit-1.0",
                "document_sha256": document.original_sha256,
                "group_evidence_hash": evidence.snapshot_hash,
                **run,
            },
            "G1",
            run["slot"],
        )
        for run in runs
    ]
    return (
        analysis_id,
        report,
        artifact(analysis_id, "plan", document.model_dump(mode="json")),
        [artifact(analysis_id, "group_evidence", evidence.model_dump(mode="json"), "G1")],
        rows,
    )


def verify(saved):
    analysis_id, report, plan_row, evidence_rows, judge_rows = saved
    return audit.verify_document_report(
        report, plan_row, evidence_rows, judge_rows, analysis_id, "test"
    )


def rehash(row):
    row.snapshot_hash = canonical_document_hash(row.snapshot_json)


def test_saved_grouped_report_replays_offline_without_provider_calls(monkeypatch):
    saved = fixture(monkeypatch)
    monkeypatch.setattr(
        evaluation,
        "complete_group",
        lambda *args, **kwargs: pytest.fail("GET audit must not call a provider"),
    )
    assert verify(saved) is True


def test_legacy_group_input_remains_reconstructable_with_original_source_view(monkeypatch):
    from app.document.packaging import LEGACY_INPUT_VERSION
    from app.judging.prompt import input_snapshot_hash

    saved = fixture(monkeypatch)
    document = audit.DocumentPlan.model_validate(saved[2].snapshot_json)
    evidence = GroupEvidenceSnapshot.model_validate(saved[3][0].snapshot_json)
    for row in saved[4]:
        run = row.snapshot_json
        legacy = audit._group_input(
            document, document.groups[0], evidence, version=LEGACY_INPUT_VERSION
        )
        run["group_input"] = legacy
        run["group_input_hash"] = input_snapshot_hash(legacy)
        run["validation_input"]["sources"] = legacy["sources"]
        run["validation_input"]["group_input_hash"] = run["group_input_hash"]
        rehash(row)
    assert verify(saved) is True


@pytest.mark.parametrize("semantic_available", [True, False])
def test_original_validation_contract_keeps_its_historical_target(monkeypatch, semantic_available):
    from tests.test_document_evaluation import semantic

    saved = fixture(monkeypatch)
    analysis_id = saved[0]
    document = audit.DocumentPlan.model_validate(saved[2].snapshot_json)
    evidence = GroupEvidenceSnapshot.model_validate(saved[3][0].snapshot_json)
    for row in saved[4]:
        run = row.snapshot_json
        run["validation_version"] = "document-validation-1.0"
        run.pop("validation_attempts", None)
        run["validation_input"]["version"] = "document-validation-1.0"
        assertions = run["validation_input"]["assertions"]
        for assertion in assertions:
            assertion.pop("validation_target")
        replies = json.loads(run["validation_call"]["raw_response"])
        replies["version"] = "document-validation-1.0"
        for item in replies["items"]:
            attributions = item.pop("attributions")
            item["semantic"] = (
                semantic(attributions[0]["evidence_ids"][0]) if semantic_available else None
            )
            for check in item["reporting_checks"]:
                check["source_value"] = next(
                    u.text
                    for u in evidence.source_units
                    if u.unit_id == check["source_unit_ids"][0]
                )
        run["validation_call"]["raw_response"] = json.dumps(replies)
        valid = audit._judge_items(run, "G1", tuple(a["assertion_id"] for a in assertions))
        slot = audit.JudgeSlot(
            slot=run["slot"],
            provider=run["provider"],
            model=run["model"],
            model_family=run["model_family"],
            base_url="https://offline.invalid",
        )
        for index, (aid, judge_item) in enumerate(valid.items()):
            assertion = document.assertion(aid)
            pack = evaluation.projected_pack(
                evidence.pack, assertion, analysis_id, evidence.claim_snapshots[aid]
            )
            local = evaluation.document_snapshot(uuid4(), pack)
            judge = evaluation.materialize_item(judge_item, pack, slot, local)
            assertions[index] = json.loads(
                json.dumps(
                    evaluation.validation_assertion_payload(
                        assertion, judge, pack, "document-validation-1.0"
                    )
                )
            )
            result = evaluation.qualify_item(
                assertion,
                evaluation.ValidationItem.model_validate_json(json.dumps(replies["items"][index])),
                judge,
                pack,
                local,
                "identified",
                ("pubmed:123",),
            )
            result["statements"] = [s.model_dump(mode="json") for s in judge_item.statements]
            run["items"][aid] = json.loads(json.dumps(result))
        rehash(row)
    assert verify(saved) is True
    assert all(
        item["position"] == ("supported" if semantic_available else None)
        for row in saved[4]
        for item in row.snapshot_json["items"].values()
    )


def test_partial_group_and_failed_provider_assessments_remain_auditable(monkeypatch):
    saved = fixture(monkeypatch, failed_slot=2)
    saved[-1].pop()
    assert verify(saved) is True


def test_source_invalid_item_can_be_unavailable_without_rejecting_its_valid_sibling(monkeypatch):
    def bad_item(data, payload):
        data["items"][1]["statements"][0]["source_unit_ids"] = ["E999.U1"]

    saved = fixture(monkeypatch, mutate_judge=bad_item)
    assert verify(saved) is True


@pytest.mark.parametrize("target", ["plan", "evidence", "judge"])
def test_changed_artifact_hash_is_rejected(monkeypatch, target):
    saved = fixture(monkeypatch)
    row = saved[2] if target == "plan" else saved[3][0] if target == "evidence" else saved[4][0]
    row.snapshot_hash = "0" * 64
    with pytest.raises(ValueError, match="hash_mismatch"):
        verify(saved)


@pytest.mark.parametrize("target", ["plan", "evidence", "judge"])
def test_foreign_analysis_artifact_is_rejected_even_with_valid_hash(monkeypatch, target):
    saved = fixture(monkeypatch)
    row = saved[2] if target == "plan" else saved[3][0] if target == "evidence" else saved[4][0]
    row.analysis_id = uuid4()
    with pytest.raises(ValueError, match="ownership_mismatch"):
        verify(saved)


def test_plan_source_hash_cannot_be_changed_by_rehashing_the_artifact(monkeypatch):
    saved = fixture(monkeypatch)
    saved[2].snapshot_json["original_sha256"] = "0" * 64
    rehash(saved[2])
    with pytest.raises(ValueError, match="Document source hash mismatch"):
        verify(saved)


@pytest.mark.parametrize("field", ["source_units", "source_quantity_catalog", "original_context"])
def test_rehashed_judge_input_cannot_diverge_from_shared_source_contract(monkeypatch, field):
    saved = fixture(monkeypatch)
    run = saved[4][0].snapshot_json
    if field == "original_context":
        run["group_input"]["original_context"] = "Another document"
    elif field == "source_units":
        run["group_input"]["sources"]["source_units"][0]["text"] = "Another source"
    else:
        run["group_input"]["sources"]["source_quantity_catalog"]["rows"] = []
    rehash(saved[4][0])
    with pytest.raises(ValueError, match="group_input_provenance_mismatch"):
        verify(saved)


def test_changed_stored_position_is_rejected_after_rehash(monkeypatch):
    saved = fixture(monkeypatch)
    saved[4][0].snapshot_json["items"]["A1"]["position"] = "contradicted"
    rehash(saved[4][0])
    with pytest.raises(ValueError, match="position_mismatch:G1:1:A1"):
        verify(saved)


def test_changed_validated_quote_is_rejected_after_rehash(monkeypatch):
    saved = fixture(monkeypatch)
    saved[4][0].snapshot_json["items"]["A1"]["reporting_checks"][0]["source_value"] = (
        "Invented quote"
    )
    rehash(saved[4][0])
    with pytest.raises(ValueError, match="validated_field_mismatch.*reporting_checks"):
        verify(saved)


def test_modified_raw_validator_response_cannot_keep_old_validated_position(monkeypatch):
    import json

    saved = fixture(monkeypatch)
    call = saved[4][0].snapshot_json["validation_call"]
    data = json.loads(call["raw_response"])
    data["items"][0]["reporting_checks"][0]["status"] = "mismatch"
    call["raw_response"] = json.dumps(data)
    saved[4][0].snapshot_json["validation_attempts"][-1] = deepcopy(call)
    rehash(saved[4][0])
    with pytest.raises(ValueError, match="position_mismatch"):
        verify(saved)


def test_running_report_before_evidence_or_model_replies_is_auditable(monkeypatch):
    saved = fixture(monkeypatch)
    assert audit.verify_document_report(saved[1], saved[2], [], [], saved[0], "test") is True


def test_duplicate_slots_cannot_supply_an_extra_quorum_vote(monkeypatch):
    saved = fixture(monkeypatch)
    saved[4].append(deepcopy(saved[4][0]))
    with pytest.raises(ValueError, match="duplicate_judge_slot"):
        verify(saved)


def test_reordered_provider_items_preserve_planned_validator_order(monkeypatch):
    def reverse(data, payload):
        data["items"].reverse()

    assert verify(fixture(monkeypatch, mutate_judge=reverse)) is True


def test_failed_chain_without_provider_responses_remains_unavailable(monkeypatch):
    saved = fixture(monkeypatch)
    row = saved[4][0]
    row.snapshot_json = {
        "version": "document-judge-audit-1.0",
        "document_sha256": saved[2].snapshot_json["original_sha256"],
        "group_evidence_hash": saved[3][0].snapshot_json["snapshot_hash"],
        "slot": 1,
        "model": "judge-one",
        "provider": "openai_compatible",
        "model_family": "one",
        "failure": "TimeoutError",
        "items": {aid: {"position": None, "failure": "TimeoutError"} for aid in ("A1", "A2")},
    }
    rehash(row)
    assert verify(saved) is True


def test_no_evaluable_assertions_static_branch_is_safe_and_cannot_hide_ready_items(monkeypatch):
    saved = fixture(monkeypatch)
    for row in saved[4]:
        row.snapshot_json = {
            "version": "document-judge-audit-1.0",
            "document_sha256": saved[2].snapshot_json["original_sha256"],
            "group_evidence_hash": saved[3][0].snapshot_json["snapshot_hash"],
            "slot": row.slot,
            "model": "judge",
            "provider": "openai_compatible",
            "model_family": "one",
            "failure": "no_evaluable_assertions",
            "items": {
                aid: {"position": None, "failure": "normalization_incomplete"}
                for aid in ("A1", "A2")
            },
        }
        rehash(row)
    with pytest.raises(ValueError, match="evaluable_assertions_claimed_empty"):
        verify(saved)
    for assertion in saved[2].snapshot_json["assertions"]:
        assertion["planning_status"] = "unresolved"
    rehash(saved[2])
    assert verify(saved) is True


@pytest.mark.parametrize("field", ["group_evidence_hash", "document_sha256"])
def test_judge_parent_hashes_cannot_be_rebound_by_rehashing_the_row(monkeypatch, field):
    saved = fixture(monkeypatch)
    saved[4][0].snapshot_json[field] = "0" * 64
    rehash(saved[4][0])
    with pytest.raises(ValueError, match="judge_parent_hash_mismatch"):
        verify(saved)


def test_frozen_quantity_catalog_cannot_be_edited_with_recomputed_outer_hash(monkeypatch):
    saved = fixture(monkeypatch)
    data = saved[3][0].snapshot_json
    data["source_quantity_catalog"]["items"][0]["values"] = ["999"]
    data["snapshot_hash"] = _snapshot_digest(
        {k: v for k, v in data.items() if k != "snapshot_hash"}
    )
    rehash(saved[3][0])
    with pytest.raises(ValueError, match="Shared quantity catalog differs"):
        verify(saved)


def test_endpoint_uses_only_parents_present_at_the_saved_report_time(monkeypatch):
    from datetime import timedelta

    from app.api.routes import analyses
    from app.document import persistence

    saved = fixture(monkeypatch)
    analysis_id, report, plan_row, evidence_rows, judge_rows = saved
    partial = build_document_report(
        analysis_id,
        audit.DocumentPlan.model_validate(plan_row.snapshot_json),
        {"G1": evidence_rows[0].snapshot_json},
        {"G1": [judge_rows[0].snapshot_json]},
        app_env="test",
        status="running",
    )
    report_row = artifact(analysis_id, "report", partial)
    for row in judge_rows[1:]:
        row.created_at += timedelta(seconds=1)
    monkeypatch.setattr(analyses, "get_run", lambda *args: None)
    monkeypatch.setattr(
        persistence,
        "latest_document_artifact",
        lambda session, id, kind: report_row if kind == "report" else plan_row,
    )
    monkeypatch.setattr(
        persistence,
        "load_document_artifacts",
        lambda *args: [plan_row, *evidence_rows, *judge_rows, report_row],
    )
    monkeypatch.setattr(
        evaluation,
        "complete_group",
        lambda *args, **kwargs: pytest.fail("GET must not make provider calls"),
    )
    result = asyncio.run(analyses.get_document_report(analysis_id, object(), settings()))
    assert result == partial
    assert result["progress"]["groups_completed"] == 0
