"""Offline protocol and conditional-policy tests, not clinical validation."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.adapters.model_catalog import discover_models
from app.evaluation.artifacts import load_retained, runtime_directory
from app.evaluation.cases import benchmark_cases
from app.evaluation.ensemble import compare as compare_ensembles
from app.evaluation.judge_bakeoff import expected_position
from app.evaluation.oracle import prepare as prepare_oracle
from app.evaluation.results import repeatability
from app.evaluation.selection import lean_selection, oracle_selection, subset_pack
from app.judging.models import JudgeSlot
from app.judging.prompt import input_snapshot_hash, prepare_judge_input, prepare_minimal_v2
from app.judging.v3 import DecisiveChecks, JudgeContentV3, derive_judge_position_v3, prepare_v3
from app.validation.evaluation_budget import EvaluationBudget, evaluation_row


def setup_case(identifier: str = "support-trial") -> tuple:
    case = next(c for c in benchmark_cases() if c.id == identifier)
    pack = case.pack
    prepared = prepare_v3(prepare_judge_input(uuid4(), pack))
    content = JudgeContentV3.model_validate_json(json.dumps({
        "assessments": [{"assessment_id": "A1", "source_id": pack.documents[0].document_id,
                         "evidence_unit_ids": ["E1.U1"], "relation": "supports_claim",
                         "scope": "aligned", "materiality": "decisive",
                         "evidence_basis": "randomized_intervention",
                         "reason_codes": ["DIRECT_FINDING"]}],
        "overall_uncertainty_reasons": [],
    }))
    return pack, prepared, content


def test_unit_only_and_qualitative_numbers() -> None:
    pack, prepared, content = setup_case()
    result = derive_judge_position_v3(content, prepared, pack)
    assert result.position == "supported"
    assert result.operational_failure is None
    assert "quote" not in content.model_dump_json()
    assert "statements" not in content.model_dump_json()


@pytest.mark.parametrize("extra", [{"label": "supported"}, {"quote": "copied"},
                                    {"schema_version": "3.0"}, {"rr": 0.85}])
def test_model_cannot_supply_protocol_verdict_or_numbers(extra: dict) -> None:
    _, _, content = setup_case()
    with pytest.raises(ValidationError):
        JudgeContentV3.model_validate_json(json.dumps({**content.model_dump(mode="json"), **extra}))


@pytest.mark.parametrize("defect", ["unknown", "owner", "text", "pack", "snapshot"])
def test_provenance_defects_are_operational_not_nei(defect: str) -> None:
    pack, prepared, content = setup_case()
    data = content.model_dump(mode="json")
    if defect == "unknown":
        data["assessments"][0]["evidence_unit_ids"] = ["E999.U1"]
    elif defect == "owner":
        data["assessments"][0]["source_id"] = "unknown-source"
    elif defect == "pack":
        pack = pack.model_copy(update={"snapshot_hash": "0" * 64})
    else:
        snapshot = json.loads(json.dumps(prepared.input_snapshot_json))
        snapshot["source_units"][0]["text"] = "tampered"
        prepared = replace(prepared, input_snapshot_json=snapshot,
                           input_snapshot_hash=input_snapshot_hash(snapshot)
                           if defect == "text" else prepared.input_snapshot_hash)
    content = JudgeContentV3.model_validate_json(json.dumps(data))
    result = derive_judge_position_v3(content, prepared, pack)
    assert result.position is None
    assert result.operational_failure == "invalid_source_reference"


@pytest.mark.parametrize("status", ["invalid", "uncertain"])
def test_crosscheck_failure_not_deleted_into_nei(status: str) -> None:
    pack, prepared, content = setup_case()
    result = derive_judge_position_v3(content, prepared, pack, crosscheck={"A1": status})
    assert result.position is None
    assert result.operational_failure == "crosscheck_failed"


def test_unknown_crosscheck_id_is_fatal() -> None:
    pack, prepared, content = setup_case()
    assert derive_judge_position_v3(content, prepared, pack, crosscheck={"A9": "valid"}
                                    ).operational_failure == "crosscheck_unavailable"


def test_crosscheck_cannot_add_a_vote_or_rationale() -> None:
    with pytest.raises(ValidationError):
        DecisiveChecks.model_validate_json(json.dumps({
            "checks": [{"assessment_id": "A1", "status": "valid", "label": "supported"}],
        }))


def test_minimal_candidate_changes_prompt_not_frozen_evidence() -> None:
    pack, _, _ = setup_case()
    original = prepare_judge_input(uuid4(), pack)
    candidate = prepare_minimal_v2(original)
    assert candidate.input_snapshot_json == original.input_snapshot_json
    assert candidate.input_snapshot_hash == original.input_snapshot_hash
    assert candidate.prompt_hash != original.prompt_hash
    assert candidate.prompt_version != original.prompt_version
    assert "For a genuinely numeric claim" in candidate.system_prompt
    assert "genuine conflict" in candidate.system_prompt


def test_repeat_metrics_do_not_hide_operational_flips() -> None:
    rows = [{"case_id": "fixture", "model": "model", "architecture": "v3", "input_hash": "a",
             "repeat": i, "position": label, "relation": "insufficient", "failure": failure}
            for i, (label, failure) in enumerate((("not_enough_evidence", None),
                                                 (None, "timeout"),
                                                 ("not_enough_evidence", None)))]
    result = next(iter(repeatability(rows).values()))
    assert result["identical_input"] is True
    assert result["position_flips"] == 2
    assert result["failures"] == {"timeout": 1}


def test_oracle_does_not_relax_normal_judge_visibility_policy() -> None:
    pack, _, _ = setup_case()
    import hashlib

    from app.retrieval.evidence_pack import canonical_pack_bytes
    docs = (pack.documents[0].model_copy(update={"evidence_role_hint": "incompatible"}),)
    digest = hashlib.sha256(canonical_pack_bytes(
        pack.claim_snapshot, pack.query_plan, docs, pack.passages, pack.selected_evidence_ids,
        pack_version=pack.evidence_pack_version,
    )).hexdigest()
    incompatible = pack.model_copy(update={"documents": docs, "snapshot_hash": digest})
    evaluated = oracle_selection(incompatible, (docs[0].document_id,))
    assert evaluated.documents[0].evidence_role_hint == "incompatible"
    with pytest.raises(ValueError, match="Incompatible"):
        prepare_judge_input(uuid4(), evaluated)


def test_oracle_retains_origin_expiry_and_source_content() -> None:
    pack, _, _ = setup_case()
    expiry = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
    result = prepare_oracle({"purge_after": expiry, "claims": [{
        "pack": {"snapshot_json": pack.model_dump(mode="json")}, "origin": "fresh control",
    }]}, {str(pack.claim_id): [pack.documents[0].document_id]})
    assert result["purge_after"] == expiry
    assert result["claims"][0]["origin"] == "fresh control"
    assert result["claims"][0]["pack"]["snapshot_json"] == pack.model_dump(mode="json")
    assert len(result["claims"]) == 5


def test_quota_exhaustion_stops_evaluation_without_credentials_or_new_calls() -> None:
    budget = EvaluationBudget(10, 30)
    async def run() -> None:
        request = httpx.Request("POST", "https://example.invalid", json={"model": "fixture"})
        token = evaluation_row.set("row-1")
        await budget.before(request)
        response = httpx.Response(403, request=request, json={"error": {
            "message": "ALL_TIME_LIMIT_EXCEEDED", "secret": "private-provider-data"}})
        await budget.after(response)
        evaluation_row.reset(token)
        with pytest.raises(ValueError, match="provider_quota_exhausted"):
            await budget.before(request)
    asyncio.run(run())
    assert len(budget.calls) == 1
    assert budget.calls[0]["evaluation_row"] == "row-1"
    assert "private-provider-data" not in json.dumps(budget.summary())


def test_parent_rct_does_not_randomize_observed_exposure() -> None:
    pack, prepared, content = setup_case("association-causal")
    result = derive_judge_position_v3(content, prepared, pack)
    assert result.position is None
    assert result.excluded_assessments["A1"] == "EXPOSURE_NOT_RANDOMIZED"


def test_fixed_suite_does_not_leak_expected_direction_through_ids() -> None:
    suite = benchmark_cases()
    assert len(suite) == 40
    assert sum(c.split == "held_out" for c in suite) == 10
    for case in suite:
        assert case.id not in case.pack.documents[0].document_id
        assert case.pack.snapshot_hash == next(c for c in benchmark_cases()
                                               if c.id == case.id).pack.snapshot_hash


def test_all_conditional_annotations_derive_without_network() -> None:
    results = {case.id: expected_position(case) for case in benchmark_cases()}
    assert results["support-trial"] == "supported"
    assert results["opposite-trial"] == "contradicted"
    assert results["association-causal"] != "supported"
    assert results["inverse-smoking"] == "contradicted"
    assert results["numeric-overclaim"] != "supported"


def test_selection_never_changes_or_deletes_source_content() -> None:
    pack, _, _ = setup_case()
    for chosen in (lean_selection(pack), oracle_selection(pack, (pack.documents[0].document_id,))):
        assert chosen.documents == pack.documents
        assert [p.passage for p in chosen.passages] == [p.passage for p in pack.passages]
    with pytest.raises(ValueError):
        subset_pack(pack, ("E999",))


def test_expired_capture_cannot_be_replayed(tmp_path: Path) -> None:
    path = tmp_path / "capture.json"
    # Test fixture creation only; no real artifact resurrection.
    path.write_text(json.dumps({"purge_after": (datetime.now(UTC) - timedelta(seconds=1)
                                              ).isoformat()}), encoding="utf-8")
    with pytest.raises(ValueError, match="Expired"):
        load_retained(path)


def test_catalog_sanitizes_and_excludes_search_and_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [
        {"id": "family/model", "type": "openai/chat-completions", "secret": "hidden"},
        {"id": "family/browser", "type": "openai/chat-completions"},
        {"id": "family/audio", "type": "audio"},
    ]}))
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kwargs: original(transport=transport, **kwargs))
    slot = JudgeSlot(slot=1, provider="openai_compatible", model="family/model",
                     model_family="family", base_url="https://example.invalid/v1", api_key="secret")
    rows = asyncio.run(discover_models(slot))
    assert [r["eligible"] for r in rows] == [True, False, False]
    assert "hidden" not in json.dumps(rows)
    assert "secret" not in json.dumps(rows)


def test_runtime_exports_cannot_escape_into_arbitrary_directories(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ignored runtime"):
        runtime_directory(tmp_path / "runtime")


def test_ensemble_does_not_manufacture_v3_votes_or_missing_audits() -> None:
    expiry = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
    data = {"purge_after": expiry, "rows": [
        {"architecture": "v3", "case_id": "support-trial", "repeat": 0,
         "model": "google/gemini-2.5-flash-lite", "position": "supported"},
        {"architecture": "v2", "case_id": "support-trial", "repeat": 0,
         "model": "google/gemini-2.5-flash-lite", "position": "supported"},
    ]}
    result = compare_ensembles(data)
    assert result["rows"] == []
    assert result["policy_changed"] is False
    assert result["purge_after"] == expiry


def test_evaluation_records_only_safe_identity_and_token_metadata() -> None:
    budget = EvaluationBudget(2, 10)
    async def run() -> None:
        request = httpx.Request("POST", "https://example.invalid", json={"model": "family/alias"})
        await budget.before(request)
        await budget.after(httpx.Response(200, request=request, json={
            "model": "family/returned", "id": "response-1", "system_fingerprint": "fp_1",
            "choices": [{"message": {"content": "private-response"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "secret": "hidden"},
        }))
    asyncio.run(run())
    record = budget.calls[0]
    assert record["model"] == "family/alias"
    assert record["returned_model"] == "family/returned"
    assert record["usage"] == {"prompt_tokens": 10, "completion_tokens": 4}
    assert "private-response" not in json.dumps(budget.summary())
    assert "hidden" not in json.dumps(budget.summary())
