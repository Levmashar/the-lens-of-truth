"""Software/decision-table controls, explicitly not a semantic medical benchmark."""

import asyncio
import json
from itertools import product
from uuid import uuid4

import httpx
import pytest
from test_reliability_slice1 import unit_judge
from test_validation_v2 import FixtureSemanticValidator

from app.judging.models import JudgeLabel
from app.judging.prompt import prepare_judge_input
from app.judging.source_units import materialize_content
from app.pipeline.claim_types import ClaimType
from app.validation.models import (
    ConclusionJustificationStatus as Status,
)
from app.validation.models import IssueCode, ValidationIssue, ValidationStatus
from app.validation.qualification import (
    ConclusionQualifierInput,
    FindingQualificationInput,
    QualificationReason,
    qualify_conclusion,
)
from app.validation.relation_cases import CASES, HUMAN_REVIEWED
from app.validation.relation_flow import claim_magnitude_alignment
from app.validation.relations import (
    ClaimRelation,
    ClaimRelationAssessment,
    ClaimRelationResponse,
    ClaimScope,
    Materiality,
    parse_relation_response,
    prepare_relation_input,
)
from app.validation.semantic import PreparedSemanticInput
from app.validation.v2 import validate_v2


def relation(
    identifier: str, direction: str, *, scope: str = "aligned", materiality: str = "decisive"
) -> ClaimRelationAssessment:
    return ClaimRelationAssessment(
        statement_id=identifier,
        relation=ClaimRelation(direction),
        scope=ClaimScope(scope),
        materiality=Materiality(materiality),
        reason="Synthetic conditional relation.",
    )


def inputs(
    label: str, *relations: ClaimRelationAssessment, design: str = "randomized_controlled_trial"
) -> ConclusionQualifierInput:
    return ConclusionQualifierInput(
        proposed_label=JudgeLabel(label),
        claim_type=ClaimType.CAUSAL,
        risk_class="standard",
        findings=tuple(
            FindingQualificationInput(statement_id=r.statement_id, study_designs=(design,))
            for r in relations
        ),
        relations=relations,
        based_on_statement_ids=tuple(r.statement_id for r in relations),
    )


@pytest.mark.parametrize(
    ("label", "directions", "expected"),
    [
        ("supported", ("supports_claim", "context_only"), "justified"),
        ("supported", ("supports_claim", "contradicts_claim"), "not_justified"),
        ("supported", ("insufficient",), "not_justified"),
        ("supported", ("contradicts_claim",), "not_justified"),
        ("contradicted", ("contradicts_claim",), "justified"),
        ("contradicted", ("insufficient",), "not_justified"),
        ("contradicted", ("supports_claim",), "not_justified"),
        ("not_enough_evidence", ("insufficient",), "justified"),
        ("not_enough_evidence", ("context_only",), "justified"),
        ("not_enough_evidence", ("uncertain",), "justified"),
        ("not_enough_evidence", ("supports_claim", "contradicts_claim"), "justified"),
        ("not_enough_evidence", ("supports_claim",), "not_justified"),
        ("not_enough_evidence", ("contradicts_claim",), "not_justified"),
    ],
)
def test_pure_qualification_table(label: str, directions: tuple[str, ...], expected: str) -> None:
    relations = tuple(relation(f"S{i + 1}", d) for i, d in enumerate(directions))
    before = inputs(label, *relations)
    first = qualify_conclusion(before)
    assert first.status.value == expected
    assert first == qualify_conclusion(before)
    assert before.proposed_label.value == label  # never flip a proposed judge


def test_exhaustive_single_finding_decisive_matrix() -> None:
    for label, direction, scope, materiality in product(
        JudgeLabel,
        ClaimRelation,
        ClaimScope,
        Materiality,
    ):
        result = qualify_conclusion(
            inputs(
                label,
                relation(
                    "S1",
                    direction,
                    scope=scope,
                    materiality=materiality,
                ),
            )
        )
        if label != JudgeLabel.NOT_ENOUGH_EVIDENCE and result.status == Status.JUSTIFIED:
            assert direction == (
                ClaimRelation.SUPPORTS
                if label == JudgeLabel.SUPPORTED
                else ClaimRelation.CONTRADICTS
            )
            assert scope in {ClaimScope.ALIGNED, ClaimScope.NARROWER}
            assert materiality == Materiality.DECISIVE


@pytest.mark.parametrize("design", ["cohort", "observational", "cross_sectional", "unknown"])
def test_existing_causal_design_gate_preserved(design: str) -> None:
    findings = (relation("S1", "supports_claim"),)
    assert qualify_conclusion(inputs("supported", *findings, design=design)).status != (
        Status.JUSTIFIED
    )
    nei = qualify_conclusion(inputs("not_enough_evidence", *findings, design=design))
    assert nei.status == Status.JUSTIFIED
    assert QualificationReason.CAUSAL_DESIGN_INSUFFICIENT in nei.reason_codes


def test_association_does_not_require_a_trial() -> None:
    data = inputs("supported", relation("S1", "supports_claim"), design="cohort")
    data = data.model_copy(update={"claim_type": ClaimType.ASSOCIATION})
    assert qualify_conclusion(data).status == Status.JUSTIFIED


def test_contextual_trial_cannot_launder_causal_design() -> None:
    data = inputs(
        "supported",
        relation("S1", "supports_claim"),
        relation("S2", "context_only", materiality="contextual"),
        design="cohort",
    )
    data = data.model_copy(
        update={
            "findings": (
                data.findings[0],
                data.findings[1].model_copy(
                    update={
                        "study_designs": ("randomized_controlled_trial",),
                    }
                ),
            )
        }
    )
    assert qualify_conclusion(data).status != Status.JUSTIFIED


def test_uncited_material_counterevidence_is_not_hidden() -> None:
    data = inputs(
        "supported", relation("S1", "supports_claim"), relation("S2", "contradicts_claim")
    )
    data = data.model_copy(update={"based_on_statement_ids": ("S1",)})
    result = qualify_conclusion(data)
    assert result.status == Status.NOT_JUSTIFIED
    assert set(result.conflicting_statement_ids) == {"S1", "S2"}


def test_required_numeric_uncertainty_and_fatal_defects_cannot_be_promoted() -> None:
    data = inputs("not_enough_evidence", relation("S1", "insufficient"))
    for code, severity, expected in [
        (IssueCode.NUMERIC_UNCERTAIN, "warning", Status.UNCERTAIN),
        (IssueCode.STATEMENT_NUMERIC_MISMATCH, "fatal", Status.NOT_JUSTIFIED),
        (IssueCode.RETRACTED_CITATION, "fatal", Status.NOT_JUSTIFIED),
        (IssueCode.PACK_HASH_MISMATCH, "fatal", Status.NOT_JUSTIFIED),
    ]:
        defect = ValidationIssue(
            target_type="judge_statement",
            target_id="S1",
            evidence_refs=("E1",),
            issue_code=code,
            severity=severity,
        )
        assert qualify_conclusion(data.model_copy(update={"defects": (defect,)})).status == expected


@pytest.mark.parametrize("ids", [("S1", "S1"), ("S2",), (), ("S1", "S2")])
def test_relation_batch_rejects_unknown_duplicate_missing_ids(ids: tuple[str, ...]) -> None:
    prepared = prepare_relation_input(
        {"original_claim": "X causes Y."},
        judge_run_id="j",
        validation_run_id="v",
        statement_ids=("S1",),
    )
    encoded = json.dumps(
        {"assessments": [relation(i, "insufficient").model_dump(mode="json") for i in ids]}
    )
    with pytest.raises(ValueError):
        parse_relation_response(encoded, prepared)


class FixtureRelations(FixtureSemanticValidator):
    def __init__(self, directions: tuple[str, ...], *, failure: Exception | None = None) -> None:
        super().__init__()
        self.directions = directions
        self.failure = failure

    async def assess_conclusion(self, prepared: PreparedSemanticInput) -> object:
        raise AssertionError("New runs MUST NOT call holistic conclusion validation")

    async def assess_relations(self, prepared: PreparedSemanticInput) -> ClaimRelationResponse:
        self.calls.append(prepared)
        assert "proposed_label" not in prepared.user_prompt
        assert "judge_conclusion" not in prepared.user_prompt
        if self.failure:
            raise self.failure
        return ClaimRelationResponse(
            assessments=tuple(
                relation(identifier, direction)
                for identifier, direction in zip(
                    prepared.statement_ids, self.directions, strict=True
                )
            )
        )


def new_judge(source: str, text: str) -> tuple[object, object]:
    old, pack = unit_judge(source, text)
    prepared = prepare_judge_input(old.evidence_pack_id, pack)
    decision = old.decision
    wire = {
        "label": decision.label,
        "statements": [
            {
                "statement_id": s.statement_id,
                "text": s.text,
                "kind": s.kind,
                "source_unit_ids": s.source_unit_ids,
            }
            for s in decision.statements
        ],
        "conclusion": decision.conclusion.model_dump(mode="json"),
        "uncertainty_reasons": decision.uncertainty_reasons,
    }
    return old.model_copy(
        update={
            "judge_run_id": uuid4(),
            "decision": materialize_content(json.dumps(wire), prepared.input_snapshot_json),
            "input_snapshot_version": prepared.input_snapshot_version,
            "input_snapshot_hash": prepared.input_snapshot_hash,
            "input_snapshot_json": prepared.input_snapshot_json,
        }
    ), pack


def test_new_contract_batches_relations_never_calls_holistic_validator() -> None:
    judge, pack = new_judge(
        "The trial measured X and Y but could not infer an effect.",
        "The trial could not infer an effect of X on Y.",
    )
    validator = FixtureRelations(("insufficient",))
    audit = asyncio.run(validate_v2(judge, pack, validator))
    assert audit.status == ValidationStatus.VALIDATED
    assert audit.validation_version == "judge-validation-2.2"
    assert [call.operation for call in validator.calls] == [
        "statement_attribution",
        "claim_relation",
    ]
    assert audit.result.relation_validation["assessments"][0]["relation"] == "insufficient"
    assert audit.result.conclusion_qualification["output"]["status"] == "justified"
    assert audit.result.conclusion_qualification["input"]["risk_class"] == "standard"
    assert (
        audit.result.conclusion_justification.validator_provenance.get(
            "deterministic_qualifier_version"
        )
        == "conclusion-qualifier-1.0"
    )


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (TimeoutError(), "relation_validator_timeout"),
        (ValueError("synthetic bad JSON"), "relation_validator_schema_failure"),
        (httpx.ConnectError("synthetic disconnected"), "relation_validator_transport_failure"),
    ],
)
def test_relation_provider_failures_are_not_scientific_insufficiency(
    failure: Exception,
    category: str,
) -> None:
    judge, pack = new_judge("The trial measured X and Y.", "The trial measured X and Y.")
    validator = FixtureRelations(("insufficient",), failure=failure)
    audit = asyncio.run(validate_v2(judge, pack, validator))
    assert audit.status == ValidationStatus.UNABLE_TO_VALIDATE
    assert audit.error_category == category
    assert audit.result.conclusion_justification.status == Status.UNABLE_TO_ASSESS


def test_historical_21_still_uses_recorded_old_flow() -> None:
    judge, pack = unit_judge("The trial measured X and Y.", "The trial measured X and Y.")
    validator = FixtureSemanticValidator()
    audit = asyncio.run(validate_v2(judge, pack, validator))
    assert audit.validation_version == "judge-validation-2.1"
    assert validator.calls[-1].operation == "conclusion_justification"
    assert "relation_validation" not in audit.result.model_dump(mode="json")


def test_relation_controls_do_not_claim_human_review_or_clinical_truth() -> None:
    assert 30 <= len(CASES) <= 50
    assert not HUMAN_REVIEWED
    assert len({c.id for c in CASES}) == len(CASES)
    assert {c.expected for c in CASES} == set(ClaimRelation)
    for case in CASES:
        encoded = json.dumps(case.payload())
        assert "expected" not in encoded
        assert "rationale" not in encoded


def test_relation_prompt_replay_uses_recorded_version() -> None:
    hashes = []
    for version in ("1.0", "1.1", "1.2"):
        prompt = prepare_relation_input(
            {"original_claim": "X causes Y."}, judge_run_id="j", validation_run_id="v",
            statement_ids=("S1",), prompt_version=f"claim-relation-{version}-2026-10-01",
        )
        hashes.append(prompt.prompt_hash)
        assert ("The study_design field" in prompt.system_prompt) == (version == "1.2")
        assert ("Explicit inability to infer" in prompt.system_prompt) == (version != "1.0")
    assert len(set(hashes)) == 3
    with pytest.raises(ValueError, match="Unknown relation prompt"):
        prepare_relation_input({}, judge_run_id="j", validation_run_id="v", statement_ids=("S1",),
                               prompt_version="unsupported")


def test_offline_qualification_replay_rejects_modified_case_or_prompt() -> None:
    from copy import deepcopy

    from app.validation.relation_qualification_eval import evaluate

    case = CASES[0]
    prepared = prepare_relation_input(
        case.payload(), judge_run_id="benchmark", validation_run_id="benchmark",
        statement_ids=("S1",),
    )
    row = {"case_id": case.id, "input": json.loads(prepared.user_prompt.split("\n", 1)[1]),
           "prompt_hash": prepared.prompt_hash,
           "response": relation("S1", "supports_claim").model_dump(mode="json")}
    artifact = {"models": [{"model": "fixture", "baseline": [row]}]}
    result = evaluate(artifact)
    assert result["model_calls"] == 0
    assert result["models"][0]["false_qualified"] == 0
    assert result["models"][0]["false_rejected"] == 0
    for field, value in [("prompt_hash", "0" * 64), ("input", {"original_claim": "tampered"})]:
        corrupted = deepcopy(artifact)
        corrupted["models"][0]["baseline"][0][field] = value
        with pytest.raises(ValueError):
            evaluate(corrupted)


@pytest.mark.parametrize(("claim", "finding", "expected"), [
    ("X reduces Y risk by 85%.", "RR 0.85 (95% CI 0.82-0.88).", "mismatch"),
    ("X reduces Y risk by about 15%.", "RR 0.85 (95% CI 0.82-0.88).", "aligned"),
    ("X reduces Y risk by 15%.", "HR 0.85 (95% CI 0.82-0.88).", "uncertain"),
    ("X reduces Y risk by 15%.", "OR 0.85 (95% CI 0.82-0.88).", "uncertain"),
    ("X reduces Y.", "RR 0.85 (95% CI 0.82-0.88).", "not_applicable"),
])
def test_claim_magnitude_does_not_launder_a_correct_finding(
    claim: str, finding: str, expected: str,
) -> None:
    from app.validation.models import NumericAlignment

    alignment = claim_magnitude_alignment(claim, finding)
    assert alignment.value == expected
    if alignment in {NumericAlignment.MISMATCH, NumericAlignment.UNCERTAIN}:
        for label, direction, status in [
            ("supported", "supports_claim", Status.NOT_JUSTIFIED),
            ("contradicted", "contradicts_claim", Status.JUSTIFIED),
            ("not_enough_evidence", "supports_claim", Status.JUSTIFIED),
        ]:
            data = inputs(label, relation("S1", direction))
            data = data.model_copy(update={"findings": (
                data.findings[0].model_copy(update={"claim_magnitude_alignment": alignment}),
            )})
            assert qualify_conclusion(data).status == status


def test_observational_synthesis_label_cannot_promote_weak_causality() -> None:
    for direction in ("supports_claim", "contradicts_claim"):
        data = inputs("supported", relation("S1", direction), design="meta_analysis")
        data = data.model_copy(update={"findings": (
            data.findings[0].model_copy(update={
                "deterministic_relations": ("weaker_than_claim",),
            }),
        )})
        assert qualify_conclusion(data).status == Status.NOT_JUSTIFIED
        assert qualify_conclusion(data.model_copy(update={
            "proposed_label": JudgeLabel.NOT_ENOUGH_EVIDENCE,
        })).status == Status.JUSTIFIED


@pytest.mark.parametrize("integrity", ["unknown", "expression_of_concern", "retracted"])
def test_incomplete_integrity_cannot_become_scientific_nei(integrity: str) -> None:
    data = inputs("not_enough_evidence", relation("S1", "insufficient"))
    data = data.model_copy(update={"findings": (
        data.findings[0].model_copy(update={"integrity_statuses": (integrity,)}),
    )})
    result = qualify_conclusion(data)
    assert result.status == Status.UNCERTAIN
    assert result.reason_codes == (QualificationReason.INTEGRITY_NOT_ESTABLISHED,)


def test_relation_adapter_has_one_batch_no_tools_and_strict_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.adapters.entailment import OpenAICompatibleEntailmentValidator

    requests = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "assessments": [relation("S1", "supports_claim").model_dump(mode="json"),
                            relation("S2", "context_only").model_dump(mode="json")],
        })}}]})

    class OfflineClient(httpx.AsyncClient):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", OfflineClient)
    prepared = prepare_relation_input(
        {"original_claim": "X causes Y.", "validated_statements": [
            {"statement_id": "S1", "text": "X caused Y."},
            {"statement_id": "S2", "text": "The trial recruited adults."},
        ]}, judge_run_id="j", validation_run_id="v", statement_ids=("S1", "S2"),
    )
    adapter = OpenAICompatibleEntailmentValidator(
        "openai_compatible", "fixture", "https://example.test/v1", "fixture-secret",
    )
    response = asyncio.run(adapter.assess_relations(prepared))
    assert len(requests) == 1
    assert tuple(r.statement_id for r in response.assessments) == ("S1", "S2")
    assert not {"tools", "tool_choice", "web_search_options"} & requests[0].keys()
    assert requests[0]["response_format"]["json_schema"]["strict"]
    assert "proposed_label" not in str(requests[0])
    # Audit identity does not change the prompt used in paired stability trials.
    repeated = prepare_relation_input(
        {"original_claim": "X causes Y.", "validated_statements": [
            {"statement_id": "S1", "text": "X caused Y."},
            {"statement_id": "S2", "text": "The trial recruited adults."},
        ]}, judge_run_id="different", validation_run_id="different", statement_ids=("S1", "S2"),
    )
    assert repeated.prompt_hash == prepared.prompt_hash


def test_evaluation_budget_counts_physical_calls_and_redacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.validation.evaluation_budget import EvaluationBudget

    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    class OfflineClient(httpx.AsyncClient):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", OfflineClient)
    budget = EvaluationBudget(1, 30)

    async def exercise() -> None:
        with budget.measure():
            async with httpx.AsyncClient() as client:
                await client.post("https://example.test/v1", json={"model": "fixture"},
                                  headers={"Authorization": "Bearer private"})
                with pytest.raises(ValueError, match="evaluation_call_budget_exceeded"):
                    await client.post("https://example.test/v1", json={"model": "fixture"})

    asyncio.run(exercise())
    summary = budget.summary()
    assert summary["http_calls"] == 1
    assert summary["input_tokens"] == 10 and summary["output_tokens"] == 5
    assert "private" not in str(summary) and "Authorization" not in str(summary)


@pytest.mark.parametrize(("mode", "risk", "count", "accepted"), [
    ("fixture_or_evaluation", "standard", 1, True),
    ("production", "standard", 1, False),
    ("production", "standard", 2, True),
    ("fixture_or_evaluation", "high", 1, False),
    ("production", "high", 2, False),
    ("production", "high", 3, True),
])
def test_22_keeps_thresholds_and_rechecks_full_audit(
    mode: str, risk: str, count: int, accepted: bool,
) -> None:
    from dataclasses import replace

    from app.verdict.models import AggregationContext, AggregationInput, ClaimFacts
    from app.verdict.policy import POLICY_V3
    from app.verdict.service import VerdictService

    first, pack = new_judge("X caused Y in the randomized trial.",
                            "The randomized trial reported that X caused Y.")
    decision = first.decision.model_copy(update={"label": JudgeLabel.SUPPORTED})
    judges = tuple(first.model_copy(update={
        "judge_run_id": uuid4(), "slot": index, "model": f"fixture-{index}",
        "model_family": f"family-{index}", "decision": decision,
        "response_json": decision.model_dump(mode="json"),
        "model_identity_verified": True, "model_family_verified": True,
        "model_snapshot": "fixture", "search_isolation_verified": True,
    }) for index in range(1, count + 1))
    validations = tuple(asyncio.run(validate_v2(
        j, pack, FixtureRelations(("supports_claim",)), risk_class=risk,
    )) for j in judges)
    request = AggregationInput(
        claim_id=pack.claim_id, evidence_pack_id=first.evidence_pack_id,
        evidence_pack_hash=pack.snapshot_hash, judge_run_ids=tuple(j.judge_run_id for j in judges),
        judge_validation_run_ids=tuple(v.id for v in validations), mode=mode,
        policy_version=POLICY_V3.version,
    )
    context = AggregationContext(
        claim=ClaimFacts(
            claim_id=pack.claim_id, normalization_status="normalized", risk_class=risk,
        ),
        pack=pack, stored_pack_hash=pack.snapshot_hash, retrieval_status="ok",
        judges=judges, validations=validations,
    )
    # Test-local approval, not a deployed policy or .env change.
    policy = replace(POLICY_V3, approved_entailment_providers=frozenset({"fixture"}))
    result = VerdictService(policy=policy).aggregate(request, context)
    assert (result.verdict.value == "supported") == accepted
    assert result.qualified_judges == count
    assert not VerdictService(policy=POLICY_V3).aggregate(
        request.model_copy(update={"mode": "production"}), context,
    ).production_qualified

    # Even otherwise approved audit data must be derived from this frozen pack.
    tampered = validations[0].result.conclusion_qualification.copy()
    tampered["input"] = {**tampered["input"], "risk_class": "high" if risk == "standard"
                         else "standard"}
    bad = validations[0].model_copy(update={"result": validations[0].result.model_copy(update={
        "conclusion_qualification": tampered,
    })})
    changed = VerdictService(policy=policy).aggregate(request, context.model_copy(update={
        "validations": (bad, *validations[1:]),
    }))
    assert changed.qualified_judges < count
    assert changed.verdict.value != "supported"
