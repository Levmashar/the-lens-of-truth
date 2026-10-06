"""A unique frozen parent ID can be audited in development, never invented."""

import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import pytest

from app.evaluation.slice41_cases import CASES, annotated_response, probe_judge
from app.judging.models import JudgeSlot, ProviderResponse
from app.judging.service import DecisionFailure, JudgeService, parse_provider_decision
from app.judging.source_units import normalize_parent_unit_ids
from app.validation.audit23 import audit_matches23
from app.validation.joint23 import validate_joint23
from app.validation.models import IssueCode, ValidationStatus
from app.validation.v2 import validate_v2
from tests.test_judging import pack_for


class StaticProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    async def evaluate(self, _slot: JudgeSlot, _prepared: object) -> ProviderResponse:
        return ProviderResponse(content=self.content)


class StaticValidator:
    provider = "fixture"
    model = "fixture"

    def __init__(self, case: object) -> None:
        self.response = annotated_response(case)

    async def assess_joint23(self, _prepared: object) -> object:
        return self.response


def test_unique_parent_is_audited_and_unknown_is_not_repaired() -> None:
    case = next(c for c in CASES if c.id == "smoking-positive")
    fixture, pack = probe_judge(case)
    assert fixture.response_json is not None
    raw = json.loads(fixture.response_json["raw_model_content"])
    raw["statements"][0]["source_unit_ids"] = ["E1"]
    content = json.dumps(raw)
    slot = JudgeSlot(slot=1, provider="fixture", model="fixture",
                     model_family="fixture", base_url="https://example.invalid/v1")
    run = asyncio.run(JudgeService(
        {"fixture": StaticProvider(content)}, axes_development=True, axes_contract="2.3",
    ).run(uuid4(), pack, (slot,), app_env="development"))[0][0]
    assert run.outcome_status == "succeeded" and run.attempt_count == 1
    assert run.response_json is not None
    assert run.response_json["source_unit_id_normalizations"] == [{
        "statement_id": "S1", "from": "E1", "to": "E1.U1",
        "rule": "unique-frozen-parent-unit-1.0",
    }]
    assert run.decision is not None
    assert run.decision.statements[0].source_unit_ids == ("E1.U1",)
    assert json.loads(run.response_json["raw_model_content"])[
        "statements"][0]["source_unit_ids"] == ["E1"]
    audit = asyncio.run(validate_joint23(run, pack, StaticValidator(case)))
    assert audit.status == ValidationStatus.VALIDATED
    assert audit_matches23(run, audit, pack, "standard")
    tampered = run.model_copy(update={"response_json": {
        **run.response_json, "source_unit_id_normalizations": [{
            "statement_id": "S1", "from": "E9", "to": "E1.U1",
            "rule": "unique-frozen-parent-unit-1.0",
        }],
    }})
    assert not audit_matches23(tampered, audit, pack, "standard")


def test_invalid_or_ambiguous_parent_remains_invalid() -> None:
    case = next(c for c in CASES if c.id == "smoking-positive")
    fixture, pack = probe_judge(case)
    assert fixture.response_json is not None
    raw = json.loads(fixture.response_json["raw_model_content"])
    snapshot = deepcopy(fixture.input_snapshot_json)
    assert snapshot is not None
    raw["statements"][0]["source_unit_ids"] = ["E999"]
    assert normalize_parent_unit_ids(json.dumps(raw), snapshot)[1] == []
    raw["statements"][0]["source_unit_ids"] = ["E1"]
    units = snapshot["source_units"]
    assert isinstance(units, list)
    units.append({**units[0], "unit_id": "E1.U2"})
    assert normalize_parent_unit_ids(json.dumps(raw), snapshot)[1] == []

    slot = JudgeSlot(slot=1, provider="fixture", model="fixture",
                     model_family="fixture", base_url="https://example.invalid/v1")
    for identifier in ("E999", "E1.U999"):
        raw["statements"][0]["source_unit_ids"] = [identifier]
        run = asyncio.run(JudgeService(
            {"fixture": StaticProvider(json.dumps(raw))},
            axes_development=True, axes_contract="2.3",
        ).run(uuid4(), pack, (slot,), app_env="development"))[0][0]
        assert run.outcome_status == "failed"
        assert run.error_category == "invalid_source_unit"
    raw["statements"][0]["source_unit_ids"] = ["E1"]
    run = asyncio.run(JudgeService({"fixture": StaticProvider(json.dumps(raw))}).run(
        uuid4(), pack, (slot,), app_env="production",
    ))[0][0]
    assert run.outcome_status == "failed"
    assert run.error_category == "schema_violation"
    assert run.decision is None


def test_visible_sibling_of_selected_document_is_citable_only_in_current_development() -> None:
    pack = pack_for()
    content = json.dumps({
        "label": "not_enough_evidence", "statements": [{
            "statement_id": "S1", "text": "The frozen section discusses the studied question.",
            "qualitative_finding": "The frozen section discusses the studied question.",
            "kind": "study_finding", "source_unit_ids": ["E2"],
            "numeric_details": [], "numeric_dependency": False,
        }],
        "conclusion": {"based_on_statement_ids": ["S1"],
                       "justification": "S1 alone does not establish the proposed effect.",
                       "qualitative_justification": "S1 cannot establish the effect.",
                       "numeric_dependency": False},
        "uncertainty_reasons": ["limited_evidence"],
    })
    slot = JudgeSlot(slot=1, provider="fixture", model="fixture",
                     model_family="fixture", base_url="https://example.invalid/v1")
    run = asyncio.run(JudgeService(
        {"fixture": StaticProvider(content)}, axes_development=True, axes_contract="2.3",
    ).run(uuid4(), pack, (slot,), app_env="development"))[0][0]
    assert run.outcome_status == "succeeded"
    assert run.decision is not None
    assert run.decision.statements[0].evidence_refs[0].evidence_id == "E2"
    preflight = asyncio.run(validate_v2(run, pack, None))
    assert IssueCode.CITATION_NOT_SELECTED not in {
        issue.issue_code for issue in preflight.result.targeted_issues
    }
    assert not preflight.result.fatal_issue_codes
    assert run.input_snapshot_json is not None
    normalized = normalize_parent_unit_ids(content, run.input_snapshot_json)[0]
    with pytest.raises(DecisionFailure, match="invalid_evidence_citation"):
        parse_provider_decision(normalized, pack.selected_evidence_ids,
                                snapshot=run.input_snapshot_json)
