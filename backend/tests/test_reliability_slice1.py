"""Slice 1 contract regressions; semantic mocks do not measure medical accuracy."""

import asyncio
import json
from argparse import Namespace
from dataclasses import replace
from uuid import uuid4

import pytest
from test_judging import FakeProvider, slot, unit_content
from test_validation_v2 import NOW, FixtureSemanticValidator, pack_for

from app.judging.models import JudgeRun, ProviderResponse
from app.judging.prompt import input_snapshot_hash, prepare_judge_input
from app.judging.service import DecisionFailure, JudgeService, parse_provider_decision
from app.judging.source_units import materialize_content
from app.validation.assertion_numeric import compare_assertion_numbers
from app.validation.models import IssueCode, NumericAlignment, ValidationStatus
from app.validation.numeric import compare_statement_numbers
from app.validation.replay import quote_diagnostic
from app.validation.v2 import validate_v2

SOURCE = ("The reduction in invasive melanomas was substantial (n = 3 in active v 11 "
          "in control group; HR, 0.27; 95% CI, 0.08 to 0.97) compared with that for "
          "preinvasive melanomas (HR, 0.73; 95% CI, 0.29 to 1.81).")
ASSERTION = "The trial found fewer invasive melanomas (3 vs 11; HR 0.27, 95% CI 0.08 to 0.97)."


def unit_judge(source: str, text: str) -> tuple[JudgeRun, object]:
    pack = pack_for("X causes Y.", (("RESULTS", source),))
    prepared = prepare_judge_input(uuid4(), pack, version="judge-input-2.1")
    unit = next(u for u in prepared.input_snapshot_json["source_units"] if u["text"] == source)
    content = {"label": "not_enough_evidence", "statements": [{
        "statement_id": "S1", "text": text, "kind": "study_finding",
        "source_unit_ids": [unit["unit_id"]],
    }], "conclusion": {"based_on_statement_ids": ["S1"],
                        "justification": "S1 describes the result at its actual study scope."},
               "uncertainty_reasons": []}
    decision = materialize_content(json.dumps(content), prepared.input_snapshot_json)
    return JudgeRun(
        judge_run_id=uuid4(), claim_id=pack.claim_id, evidence_pack_id=prepared.pack_id,
        evidence_pack_hash=pack.snapshot_hash, slot=1, provider="fixture", model="fixture",
        model_family="fixture", prompt_version="judge-2.5-2026-10-01",
        prompt_hash=prepared.prompt_hash, input_snapshot_version=prepared.input_snapshot_version,
        input_snapshot_hash=prepared.input_snapshot_hash,
        input_snapshot_json=json.loads(json.dumps(prepared.input_snapshot_json)),
        requested_at=NOW, responded_at=NOW, latency_ms=0, attempt_count=1,
        outcome_status="succeeded", decision=decision,
    ), pack


def test_exact_observed_sunscreen_parser_defect_before_and_after() -> None:
    assert compare_statement_numbers(ASSERTION, SOURCE)[0] == NumericAlignment.UNCERTAIN
    result = compare_assertion_numbers(ASSERTION, (SOURCE,))
    assert result.status == NumericAlignment.ALIGNED
    judge, pack = unit_judge(SOURCE, ASSERTION)
    run = asyncio.run(validate_v2(judge, pack, FixtureSemanticValidator()))
    assert run.status == ValidationStatus.VALIDATED
    assert not run.result.warnings


@pytest.mark.parametrize(("statement", "source", "expected"), [
    ("The estimate was not statistically significant.",
     "RR 0.85, 95% CI 0.70-1.04; HR 0.95, 95% CI 0.80-1.12.", "not_applicable"),
    ("The trial reported 85% risk reduction.", "RR 0.85.", "mismatch"),
    ("The trial reported 15% risk reduction.", "RR 0.85.", "aligned"),
    ("The trial reported OR 0.85.", "RR 0.85.", "mismatch"),
    ("The trial reported HR 0.85.", "OR 0.85.", "mismatch"),
    ("The trial reported RR 0.80.", "RR 0.15.", "mismatch"),
    ("The trial reported a 15% reduction.", "A 15% reduction was reported.", "aligned"),
    ("The dose was 80 mg.", "The dose was not stated.", "uncertain"),
    ("The study reports RR 0.85.", "RR 0.85 and RR 0.95.", "aligned"),
    ("The study reports RR 0.81.", "RR 0.85 and RR 0.95.", "uncertain"),
    ("RR 0.85, 95% CI 0.70-1.04.", "RR 0.85, 99% CI 0.70-1.04.", "mismatch"),
    ("HR 1, 95% CI 0.70-1.04.",
     "HR 1, 95% CI 0.50-1.50; HR 0.85, 95% CI 0.70-1.04.", "mismatch"),
    ("The comparison was smoking 20 cigarettes daily.",
     "The comparison was smoking 20 cigarettes per day.", "aligned"),
    ("The comparison was smoking 25 cigarettes daily.",
     "The comparison was smoking 20 cigarettes per day.", "mismatch"),
])
def test_assertion_numeric_cases(statement: str, source: str, expected: str) -> None:
    assert compare_assertion_numbers(statement, (source,)).status.value == expected


def test_backend_units_have_exact_offsets_content_hash_and_context() -> None:
    judge, pack = unit_judge(SOURCE, "The study described invasive melanoma outcomes.")
    snapshot = judge.input_snapshot_json
    passage_map = {p.evidence_id: p for p in pack.passages}
    for unit in snapshot["source_units"]:
        passage = passage_map[unit["evidence_id"]].passage
        assert unit["text"] == passage.text[unit["start"]:unit["end"]]
        assert unit["passage_sha256"] == passage.content_sha256
        assert unit["document_sha256"]
        assert unit["section"] == passage.section
    assert judge.decision.statements[0].evidence_refs[0].quote == SOURCE
    assert judge.input_snapshot_hash == input_snapshot_hash(snapshot)


def test_unknown_unit_and_model_copied_metadata_fail_closed() -> None:
    judge, _ = unit_judge(SOURCE, "The trial reported invasive melanomas.")
    wire = json.loads(unit_content(judge.decision.model_dump_json().replace('"2.1"', '"2.0"')))
    # unit_content is a transport fixture helper; production never accepts copied refs.
    wire["statements"][0]["source_unit_ids"] = ["E999.U1"]
    with pytest.raises(DecisionFailure, match="invalid_source_unit"):
        parse_provider_decision(json.dumps(wire), (), snapshot=judge.input_snapshot_json)
    wire["schema_version"] = "2.1"
    with pytest.raises(DecisionFailure, match="schema_violation"):
        parse_provider_decision(json.dumps(wire), (), snapshot=judge.input_snapshot_json)


@pytest.mark.parametrize(("field", "value"), [
    ("text", "Fabricated source."), ("passage_sha256", "0" * 64),
    ("document_sha256", "0" * 64), ("start", 1),
])
def test_corrupt_snapshot_and_forged_materialized_quote_are_rejected(
    field: str, value: object,
) -> None:
    judge, pack = unit_judge(SOURCE, "The trial reported invasive melanomas.")
    mutated = json.loads(json.dumps(judge.input_snapshot_json))
    mutated["source_units"][0][field] = value
    run = asyncio.run(validate_v2(judge.model_copy(update={
        "input_snapshot_json": mutated, "input_snapshot_hash": input_snapshot_hash(mutated),
    }), pack, FixtureSemanticValidator()))
    assert IssueCode.PACK_HASH_MISMATCH in run.result.fatal_issue_codes
    ref = judge.decision.statements[0].evidence_refs[0]
    statement = judge.decision.statements[0].model_copy(update={
        "evidence_refs": (ref.model_copy(update={"quote": "Invented conclusion."}),),
    })
    run = asyncio.run(validate_v2(judge.model_copy(update={
        "decision": judge.decision.model_copy(update={"statements": (statement,)}),
    }), pack, FixtureSemanticValidator()))
    assert IssueCode.PACK_HASH_MISMATCH in run.result.fatal_issue_codes


def test_correct_reference_does_not_certify_wrong_paraphrase() -> None:
    judge, pack = unit_judge("X and Y were not associated.", "X and Y were associated.")
    from app.validation.models import StatementAttributionStatus

    validator = FixtureSemanticValidator(statement_statuses={
        "S1": StatementAttributionStatus.CONTRADICTED_BY_SOURCES,
    })
    run = asyncio.run(validate_v2(judge, pack, validator))
    assert run.status == ValidationStatus.INVALID


def test_numeric_issue_records_exact_assertion_and_conclusion_dependency() -> None:
    judge, pack = unit_judge("X and Y were studied.", "The dose was 80 mg.")
    run = asyncio.run(validate_v2(judge, pack, FixtureSemanticValidator()))
    issue = next(i for i in run.result.targeted_issues
                 if i.issue_code == IssueCode.NUMERIC_UNCERTAIN)
    assert issue.target_id == "S1"
    assert issue.measure_type == "dose"
    assert issue.numeric_diagnostic["reason"] == "quantity_assignment_unresolved"
    assert issue.conclusion_dependency is True
    assert run.status != ValidationStatus.VALIDATED


def test_quote_classification_never_accepts_changed_quotes() -> None:
    assert quote_diagnostic("24\u2009613", "24\u200a613")["category"] == "whitespace"
    assert quote_diagnostic("X ... Y", "X and Y")["category"] == "noncontiguous_quote"


def test_correct_user_magnitude_contrast_and_wrong_user_number() -> None:
    source = "The trial found a 15% reduction."
    statement = "The trial found a 15% reduction, below the claimed 80%."
    assert compare_assertion_numbers(statement, (source,), user_claim="X reduces Y by 80%.") \
        .status == NumericAlignment.ALIGNED
    assert compare_assertion_numbers(statement, (source,), user_claim="X reduces Y by 50%.") \
        .status == NumericAlignment.MISMATCH


@pytest.mark.parametrize(("statement", "source"), [
    ("The meta-analysis included 23 studies.", "A total of 23 relevant studies were identified."),
    ("The trial included residents aged 25–75.", "Residents age 25 to 75 years were enrolled."),
    ("The study included 24,613 Finnish male smokers aged 50–69.",
     "Among 24\u200a613 Finnish male smokers aged 50-69 years."),
    ("The latency estimate was 15-year.", "Latency was approximately 15 years."),
])
def test_observed_numerical_metadata_and_context_are_typed(statement: str, source: str) -> None:
    assert compare_assertion_numbers(statement, (source,)).status == NumericAlignment.ALIGNED


def test_interval_from_another_estimate_is_rejected() -> None:
    assert compare_assertion_numbers(
        "The trial reported HR 0.27 (95% CI 0.29-1.81).", (SOURCE,),
    ).status == NumericAlignment.MISMATCH


def test_failed_output_audits_safe_field_paths_and_visible_response() -> None:
    runs, _ = asyncio.run(JudgeService({"fake": FakeProvider('{"label":"supported"}')}).run(
        uuid4(), pack_for("X causes Y.", (("RESULTS", "X and Y were studied."),)), (slot(1),),
    ))
    failed = runs[0]
    assert failed.decision is None
    diagnostics = failed.response_json["rejected_responses"]
    assert diagnostics[0]["content"] == '{"label":"supported"}'
    assert diagnostics[0]["schema_errors"]
    assert "input" not in str(diagnostics[0]["schema_errors"])


def test_all_judges_share_source_units_and_no_model_metadata_is_required() -> None:
    pack = pack_for("X causes Y.", (("RESULTS", "X and Y were studied."),))
    runs, _ = asyncio.run(JudgeService({"fake": FakeProvider()}).run(
        uuid4(), pack, (slot(1), slot(2), slot(3)),
    ))
    assert len({r.input_snapshot_hash for r in runs}) == 1
    assert all(r.decision.schema_version == "2.2" and not r.schema_version_inferred for r in runs)


def test_optional_numeric_detail_needs_fresh_bounded_revision_not_silent_acceptance() -> None:
    judge, pack = unit_judge("X caused Y in the trial. Published in 2020.",
                             "The trial reported an effect of X on Y.")
    optional = judge.decision.statements[0].model_copy(update={
        "statement_id": "S2", "text": "The trial was published in 2020.", "kind": "study_method",
    })
    judge = judge.model_copy(update={"decision": judge.decision.model_copy(update={
        "statements": (*judge.decision.statements, optional),
    })})
    audit = asyncio.run(validate_v2(judge, pack, FixtureSemanticValidator()))
    assert audit.status == ValidationStatus.PARTIALLY_VALIDATED
    issue = audit.result.targeted_issues[0]
    assert issue.issue_code == IssueCode.NUMERIC_UNCERTAIN
    assert issue.conclusion_dependency is False
    assert issue.numeric_diagnostic["asserted_tokens"] == [
        {"text": "2020", "start": 27, "end": 31},
    ]

    class RevisionProvider:
        async def evaluate(self, judge_slot: object, prepared: object) -> ProviderResponse:
            # Exact same source input: only the optional unsupported prose changes.
            assert prepared.input_snapshot_hash == judge.input_snapshot_hash
            return ProviderResponse(content=json.dumps({
                "label": "not_enough_evidence", "statements": [{
                    "statement_id": "S1", "text": "The trial reported an effect of X on Y.",
                    "kind": "study_finding", "source_unit_ids": ["E1.U1"],
                }], "conclusion": {"based_on_statement_ids": ["S1"],
                                    "justification": "The result has the trial's actual scope."},
                "uncertainty_reasons": [],
            }))

    service = JudgeService({"fixture": RevisionProvider()})
    configured = slot(1).model_copy(update={"provider": "fixture", "model": "fixture"})
    child = asyncio.run(service.revise(judge, audit, pack, configured))
    assert child.revision_of_judge_run_id == judge.judge_run_id
    assert child.semantic_revision_number == child.attempt_count == 1
    assert child.input_snapshot_hash == judge.input_snapshot_hash
    assert len(judge.decision.statements) == 2
    child_audit = asyncio.run(validate_v2(child, pack, FixtureSemanticValidator()))
    assert child_audit.status == ValidationStatus.VALIDATED
    with pytest.raises(ValueError, match="not eligible"):
        asyncio.run(service.revise(child, child_audit, pack, configured))


def test_diagnostics_redact_credentials_without_dropping_clinical_numbers() -> None:
    from app.core.diagnostics import sanitize_diagnostic

    sanitized = sanitize_diagnostic({"api_key": "secret", "content":
                                     "Bearer randomtoken configuredkey HR 0.27; password=secret"},
                                    ("configuredkey",))
    assert "randomtoken" not in str(sanitized)
    assert "configuredkey" not in str(sanitized)
    assert "secret" not in str(sanitized)
    assert "HR 0.27" in sanitized["content"]


def test_failed_model_response_diagnostic_redacts_slot_credential() -> None:
    configured = slot(1).model_copy(update={"api_key": "private-test-key"})
    runs, _ = asyncio.run(JudgeService({"fake": FakeProvider('private-test-key')}).run(
        uuid4(), pack_for("X causes Y.", (("RESULTS", "X and Y were studied."),)), (configured,),
    ))
    assert "private-test-key" not in str(runs[0].response_json)
    assert "[REDACTED]" in str(runs[0].response_json)


def test_observed_over_600_character_semantic_reason_has_bounded_contract() -> None:
    from pydantic import ValidationError

    from app.validation.semantic import StatementSemanticResponse

    response = {"statement_id": "S2", "evidence_ids": ["E23", "E25"],
                "status": "supported_by_sources", "scope_match": "exact", "reason": "r" * 685}
    accepted = StatementSemanticResponse.model_validate_json(json.dumps(response))
    assert len(accepted.reason) == 685
    assert accepted.status.value == response["status"]
    with pytest.raises(ValidationError) as caught:
        StatementSemanticResponse.model_validate_json(json.dumps({
            **response, "reason": "r" * 1201,
        }))
    assert caught.value.errors(include_input=False)[0]["type"] == "string_too_long"


@pytest.mark.parametrize(("mode", "risk", "count", "supported"), [
    ("fixture_or_evaluation", "standard", 1, True),
    ("production", "standard", 1, False),
    ("production", "standard", 2, True),
    ("fixture_or_evaluation", "high", 1, False),
    ("production", "high", 2, False),
    ("production", "high", 3, True),
])
def test_new_contract_keeps_existing_thresholds_and_release_gates(
    mode: str, risk: str, count: int, supported: bool,
) -> None:
    from app.judging.models import JudgeLabel
    from app.verdict.models import AggregationContext, AggregationInput, ClaimFacts
    from app.verdict.policy import POLICY_V3
    from app.verdict.service import VerdictService

    first, pack = unit_judge("X caused Y in the randomized trial.",
                             "The randomized trial reported that X caused Y.")
    decision = first.decision.model_copy(update={"label": JudgeLabel.SUPPORTED})
    judges = tuple(first.model_copy(update={
        "judge_run_id": uuid4(), "slot": index, "model": f"fixture-{index}",
        "model_family": f"family-{index}", "decision": decision,
        "response_json": decision.model_dump(mode="json"),
        "model_identity_verified": True, "model_family_verified": True,
        "model_snapshot": "test-fixture", "search_isolation_verified": True,
    }) for index in range(1, count + 1))
    validations = tuple(asyncio.run(validate_v2(j, pack, FixtureSemanticValidator()))
                        for j in judges)
    request = AggregationInput(
        claim_id=pack.claim_id, evidence_pack_id=first.evidence_pack_id,
        evidence_pack_hash=pack.snapshot_hash, judge_run_ids=tuple(j.judge_run_id for j in judges),
        judge_validation_run_ids=tuple(v.id for v in validations),
        mode=mode, policy_version=POLICY_V3.version,
    )
    context = AggregationContext(
        claim=ClaimFacts(claim_id=pack.claim_id, normalization_status="normalized",
                         risk_class=risk),
        pack=pack, stored_pack_hash=pack.snapshot_hash, retrieval_status="ok",
        judges=judges, validations=validations,
    )
    # Fixture approval is ONLY inside this test, never configuration or policy.
    test_policy = replace(POLICY_V3, approved_entailment_providers=frozenset({"fixture"}))
    result = VerdictService(policy=test_policy).aggregate(request, context)
    assert (result.verdict.value == "supported") == supported
    assert result.qualified_judges == count
    assert result.production_qualified == (mode == "production" and supported)

    # Same successful 2.1 audit remains release-blocked under the actual policy.
    production = VerdictService(policy=POLICY_V3).aggregate(
        request.model_copy(update={"mode": "production"}), context,
    )
    assert not production.production_qualified


@pytest.mark.parametrize("deadline", [30.0, 0.01])
def test_semantic_evaluation_call_and_deadline_bounds_are_real(
    monkeypatch: pytest.MonkeyPatch, deadline: float,
) -> None:
    import httpx

    from app.core.config import Settings
    from app.validation import slice1_eval

    async def respond(request: httpx.Request) -> httpx.Response:
        if deadline < 1:
            await asyncio.sleep(0.05)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "statement_id": "S1", "evidence_ids": ["E1"], "status": "supported_by_sources",
            "scope_match": "exact", "reason": "Synthetic fixture answer.",
        })}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    class OfflineClient(httpx.AsyncClient):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", OfflineClient)
    monkeypatch.setattr(slice1_eval, "Settings", lambda **kwargs: Settings(_env_file=None))
    monkeypatch.setattr(slice1_eval, "configured_slots", lambda settings: (
        slot(2).model_copy(update={"provider": "openai_compatible"}),
        slot(3).model_copy(update={"provider": "openai_compatible"}),
    ))
    result = asyncio.run(slice1_eval.evaluate(Namespace(
        judge_slot=2, validator_slot=3, max_calls=1, deadline=deadline,
        controls_limit=2, capture=[],
    )))
    assert result["http_calls"] == 1
    assert result["evaluation_failure"] == (
        "call_budget_exhausted" if deadline > 1 else "total_deadline_exceeded")
    assert "Authorization" not in str(result["call_diagnostics"])
    assert result["call_diagnostics"][0]["messages"]
