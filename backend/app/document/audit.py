"""Offline provenance and deterministic replay for saved document assessments."""

import json
from collections.abc import Iterable
from typing import Any, cast
from uuid import UUID, uuid5

from app.document.evaluation import (
    GROUP_INPUT_VERSION,
    JUDGE_VERSION,
    JudgeItem,
    ValidationItem,
    document_snapshot,
    is_reporting,
    materialize_item,
    parse_group_items,
    projected_pack,
    qualify_item,
    validation_assertion_payload,
    validation_item_type,
)
from app.document.models import DocumentGroup, DocumentPlan, canonical_document_hash
from app.document.packaging import (
    INPUT_VERSION,
    LEGACY_INPUT_VERSION,
    expand_quantity_view,
    source_view,
)
from app.document.retrieval import GroupEvidenceSnapshot
from app.judging.models import JudgeDecisionV2, JudgeSlot
from app.judging.prompt import input_snapshot_hash


def _json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _artifact(row: Any, kind: str, analysis_id: UUID) -> dict[str, Any]:
    if row is None or row.analysis_id != analysis_id or row.kind != kind:
        raise ValueError(f"document_audit_{kind}_ownership_mismatch")
    data = row.snapshot_json
    if not isinstance(data, dict) or canonical_document_hash(data) != row.snapshot_hash:
        raise ValueError(f"document_audit_{kind}_hash_mismatch")
    if data.get("version") != row.version:
        raise ValueError(f"document_audit_{kind}_version_mismatch")
    return data


def _context(plan: DocumentPlan, group: DocumentGroup) -> Any:
    return (
        plan.original_text
        if len(plan.original_text) <= 6000
        else [span.model_dump(mode="json") for span in group.context_spans]
    )


def _group_input(
    plan: DocumentPlan,
    group: DocumentGroup,
    evidence: GroupEvidenceSnapshot,
    version: str = GROUP_INPUT_VERSION,
) -> dict[str, Any]:
    assertions = [
        plan.assertion(aid)
        for aid in group.assertion_ids
        if plan.assertion(aid).checkable
        and not plan.assertion(aid).duplicate_of
        and plan.assertion(aid).planning_status == "ready"
        and (is_reporting(plan.assertion(aid)) or evidence.normalization_ready[aid])
    ]
    shared = document_snapshot(UUID(int=0), evidence.pack)
    return cast(
        dict[str, Any],
        _json(
            {
                "version": version,
                "group_id": group.group_id,
                "evidence_hash": evidence.pack.snapshot_hash,
                "original_context": _context(plan, group),
                "assertions": [a.model_dump(mode="json") for a in assertions],
                "context_links": [
                    link.model_dump(mode="json")
                    for link in plan.context_links
                    if any(link.link_id in a.context_link_ids for a in assertions)
                ],
                "source_match": evidence.source_match.model_dump(mode="json"),
                "assertion_evidence_coverage": evidence.per_assertion_evidence_ids,
                "sources": source_view(evidence.pack, shared, version=version),
            }
        ),
    )


def _judge_items(
    run: dict[str, Any], group_id: str, expected: tuple[str, ...]
) -> dict[str, JudgeItem]:
    attempts = run.get("judge_attempts", [])
    if not isinstance(attempts, list) or len(attempts) > 2:
        raise ValueError("document_audit_invalid_judge_attempts")
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError("document_audit_invalid_judge_attempt")
        if attempt.get("status") != "responded":
            if attempt.get("status") != "unavailable":
                raise ValueError("document_audit_invalid_judge_call_status")
            continue
        if not isinstance(attempt.get("raw_response"), str):
            raise ValueError("document_audit_missing_raw_judge_response")
        try:
            valid, _ = parse_group_items(
                attempt["raw_response"],
                version=JUDGE_VERSION,
                group_id=group_id,
                expected=expected,
                item_type=JudgeItem,
                allow_fence=run["group_input"]["version"] != LEGACY_INPUT_VERSION,
            )
            return valid
        except ValueError:
            # The engine retries a corrupt shared envelope, never salvages its children.
            continue
    return {}


def _verify_run(
    run: dict[str, Any],
    plan: DocumentPlan,
    group: DocumentGroup,
    evidence: GroupEvidenceSnapshot,
    analysis_id: UUID,
) -> None:
    stored = run.get("items")
    if (
        not isinstance(stored, dict)
        or any(aid not in group.assertion_ids for aid in stored)
        or any(not isinstance(item, dict) for item in stored.values())
    ):
        raise ValueError("document_audit_unknown_stored_assertion")
    if "group_input" not in run:
        # A transport/internal chain failure may precede a persisted input. It
        # cannot establish an available assessment or carry validated content.
        if not run.get("failure") or any(
            item.get("position") is not None for item in stored.values()
        ):
            raise ValueError("document_audit_missing_group_input")
        if any(
            key in item
            for item in stored.values()
            for key in ("semantic", "reporting_checks", "statements")
        ):
            raise ValueError("document_audit_failed_chain_contains_validated_content")
        if run.get("failure") == "no_evaluable_assertions":
            if _group_input(plan, group, evidence)["assertions"]:
                raise ValueError("document_audit_evaluable_assertions_claimed_empty")
            expected_static = {aid for aid in group.assertion_ids if plan.assertion(aid).checkable}
            if set(stored) != expected_static or any(
                item
                != {
                    "position": None,
                    "failure": "normalization_incomplete",
                }
                for item in stored.values()
            ):
                raise ValueError("document_audit_static_assessment_mismatch")
        if any(key in run for key in ("judge_attempts", "validation_input", "validation_call")):
            raise ValueError("document_audit_failed_chain_contains_unbound_calls")
        return
    input_version = run["group_input"].get("version")
    if input_version not in {INPUT_VERSION, LEGACY_INPUT_VERSION}:
        raise ValueError("document_audit_unknown_group_input_version")
    expected_input = _group_input(plan, group, evidence, version=input_version)
    if run["group_input"] != expected_input:
        raise ValueError("document_audit_group_input_provenance_mismatch")
    if run.get("group_input_hash") != input_snapshot_hash(expected_input):
        raise ValueError("document_audit_group_input_hash_mismatch")
    validation_version = run.get("validation_version")
    if run.get("judge_version") != JUDGE_VERSION or not isinstance(validation_version, str):
        raise ValueError("document_audit_response_contract_version_mismatch")
    item_type = validation_item_type(validation_version)
    expected = tuple(a["assertion_id"] for a in expected_input["assertions"])
    slot = JudgeSlot(
        slot=run["slot"],
        provider=run["provider"],
        model=run["model"],
        model_family=run["model_family"],
        # Replay does not use a provider URL or credentials.
        base_url="https://offline.invalid/",
    )
    valid = _judge_items(run, group.group_id, expected)
    projections = {}
    validation_assertions = []
    for aid in expected:
        if aid not in valid:
            continue
        judge_item = valid[aid]
        assertion = plan.assertion(aid)
        try:
            projection = projected_pack(
                evidence.pack, assertion, analysis_id, evidence.claim_snapshots[aid]
            )
            local = document_snapshot(UUID(int=0), projection)
            if local["source_units"] != expected_input["sources"]["source_units"] or local[
                "source_quantity_catalog"
            ] != (
                expand_quantity_view(expected_input["sources"]["source_quantity_catalog"])
                if input_version == INPUT_VERSION
                else expected_input["sources"]["source_quantity_catalog"]
            ):
                raise ValueError("document_audit_local_source_snapshot_mismatch")
            judge = materialize_item(judge_item, projection, slot, local)
            allowed = set(evidence.per_assertion_evidence_ids[aid])
            if not isinstance(judge.decision, JudgeDecisionV2):
                raise ValueError("document_audit_invalid_projected_decision")
            if input_version == LEGACY_INPUT_VERSION and any(
                ref.evidence_id not in allowed
                for statement in judge.decision.statements
                for ref in statement.evidence_refs
            ):
                raise ValueError("source_outside_assertion_evidence_coverage")
            validation_assertions.append(
                validation_assertion_payload(assertion, judge, projection, validation_version)
            )
            projections[aid] = (judge, projection, local)
        except (ValueError, KeyError):
            continue
    validation_items: dict[str, ValidationItem] = {}
    if projections:
        expected_validation = _json(
            {
                "version": validation_version,
                "group_id": group.group_id,
                "group_input_hash": run["group_input_hash"],
                "original_context": _context(plan, group),
                "sources": expected_input["sources"],
                "source_match": expected_input["source_match"],
                "assertions": validation_assertions,
                "context_links": expected_input["context_links"],
            }
        )
        if run.get("validation_input") != expected_validation:
            raise ValueError("document_audit_validation_input_provenance_mismatch")
        call = run.get("validation_call", {})
        if not isinstance(call, dict):
            raise ValueError("document_audit_invalid_validator_call")
        attempts = run.get("validation_attempts")
        if attempts is not None and (
            not isinstance(attempts, list)
            or not 1 <= len(attempts) <= 2
            or attempts[-1] != call
            or any(not isinstance(attempt, dict) for attempt in attempts)
        ):
            raise ValueError("document_audit_invalid_validator_attempts")
        if call.get("status") == "responded":
            if not isinstance(call.get("raw_response"), str):
                raise ValueError("document_audit_missing_raw_validator_response")
            try:
                validation_items, _ = parse_group_items(
                    call["raw_response"],
                    version=validation_version,
                    group_id=group.group_id,
                    expected=tuple(projections),
                    item_type=item_type,
                    allow_fence=input_version != LEGACY_INPUT_VERSION,
                )
            except ValueError:
                pass
        elif call.get("status") != "unavailable":
            raise ValueError("document_audit_invalid_validator_call_status")
    for aid in expected:
        replay: dict[str, Any] = {"position": None}
        if aid in projections and aid in validation_items:
            judge, projection, local = projections[aid]
            try:
                replay = qualify_item(
                    plan.assertion(aid),
                    validation_items[aid],
                    judge,
                    projection,
                    local,
                    evidence.source_match.status,
                    evidence.source_match.matched_document_ids,
                )
                replay["statements"] = [s.model_dump(mode="json") for s in valid[aid].statements]
            except (ValueError, KeyError):
                replay = {"position": None}
        item = stored.get(aid)
        if not isinstance(item, dict) or item.get("position") != replay["position"]:
            raise ValueError(
                f"document_audit_position_mismatch:{group.group_id}:{run['slot']}:{aid}"
            )
        for key in (
            "reason_codes",
            "reporting_checks",
            "semantic",
            "attributions",
            "interpretation_limits",
            "statements",
        ):
            if key in replay and _json(item.get(key)) != _json(replay[key]):
                raise ValueError(
                    f"document_audit_validated_field_mismatch:{group.group_id}:{aid}:{key}"
                )
            if key not in replay and key in item:
                raise ValueError(f"document_audit_unvalidated_field:{group.group_id}:{aid}:{key}")
    for aid, item in stored.items():
        if aid not in expected and (
            item.get("position") is not None
            or is_reporting(plan.assertion(aid))
            or evidence.normalization_ready[aid]
        ):
            raise ValueError(
                f"document_audit_unexpected_qualified_assertion:{group.group_id}:{aid}"
            )


def verify_document_report(
    report: dict[str, Any],
    plan_artifact: Any,
    group_evidence_artifacts: Iterable[Any],
    group_judge_audits: Iterable[Any],
    analysis_id: UUID,
    app_env: str,
) -> bool:
    """Verify immutable parents and replay provider replies without I/O or model calls.

    Public projection equality is checked by the endpoint against these verified
    parents. Running/no-response/unresolved checks remain unavailable; invalid
    shared provenance always fails closed rather than becoming medical NEI.
    """
    if app_env not in {"development", "test", "staging", "production"}:
        raise ValueError("document_audit_invalid_environment")
    if report.get("version") != "document-report-1.0" or report.get("analysis_id") != str(
        analysis_id
    ):
        raise ValueError("document_audit_report_identity_mismatch")
    plan = DocumentPlan.model_validate(_artifact(plan_artifact, "plan", analysis_id))
    evidence_by_group = {}
    for row in group_evidence_artifacts:
        data = _artifact(row, "group_evidence", analysis_id)
        evidence = GroupEvidenceSnapshot.model_validate(data)
        if (
            row.group_id != evidence.group_id
            or evidence.group_id not in {g.group_id for g in plan.groups}
            or evidence.document_sha256 != plan.original_sha256
        ):
            raise ValueError("document_audit_evidence_document_mismatch")
        if evidence.group_id in evidence_by_group:
            raise ValueError("document_audit_duplicate_group_evidence")
        group = plan.group(evidence.group_id)
        if set(evidence.claim_snapshots) != set(group.assertion_ids):
            raise ValueError("document_audit_claim_snapshot_coverage_mismatch")
        for aid, claim in evidence.claim_snapshots.items():
            assertion = plan.assertion(aid)
            if (
                claim.claim_id != uuid5(analysis_id, aid)
                or claim.raw_text != assertion.source_text
                or claim.normalized_text != assertion.normalized_text
            ):
                raise ValueError(f"document_audit_claim_source_mismatch:{aid}")
        document_ids = {d.document_id for d in evidence.pack.documents}
        if not set(evidence.source_match.matched_document_ids) <= document_ids:
            raise ValueError("document_audit_unknown_matched_document")
        shared = document_snapshot(UUID(int=0), evidence.pack)
        if (
            shared["source_units"] != [u.model_dump(mode="json") for u in evidence.source_units]
            or shared["source_quantity_catalog"] != evidence.source_quantity_catalog
        ):
            raise ValueError("document_audit_shared_catalog_mismatch")
        evidence_by_group[evidence.group_id] = evidence
    seen = set()
    for row in group_judge_audits:
        run = _artifact(row, "group_judge", analysis_id)
        if (
            row.group_id not in evidence_by_group
            or row.slot != run.get("slot")
            or row.slot not in {1, 2, 3}
        ):
            raise ValueError("document_audit_judge_evidence_ownership_mismatch")
        key = (row.group_id, row.slot)
        if key in seen:
            raise ValueError("document_audit_duplicate_judge_slot")
        seen.add(key)
        evidence = evidence_by_group[row.group_id]
        if (
            run.get("document_sha256") != plan.original_sha256
            or run.get("group_evidence_hash") != evidence.snapshot_hash
        ):
            raise ValueError("document_audit_judge_parent_hash_mismatch")
        _verify_run(run, plan, plan.group(row.group_id), evidence, analysis_id)
    return True
