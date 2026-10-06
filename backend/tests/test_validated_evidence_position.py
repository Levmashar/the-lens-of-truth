"""Saved four-case replays and adversarial controls; never model/network calls."""

import asyncio
import gzip
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.adapters.judge import OpenAICompatibleJudgeProvider
from app.judging.compact24 import frozen_response_matches24
from app.judging.compact25 import frozen_response_matches25, prepare_compact25
from app.judging.models import JudgeLabel, JudgeRun, JudgeSlot, ProviderResponse
from app.judging.service import JudgeService
from app.judging.source_units import JudgeContent24, JudgeContent25, materialize_content
from app.report.builder import build_report
from app.retrieval.models import EvidencePack
from app.validation.audit25 import audit_matches25
from app.validation.joint23 import JointResponse23
from app.validation.joint24 import qualification_input24, validate_joint24
from app.validation.models import StatementAttributionStatus
from app.validation.position import derive_position
from app.verdict.models import AggregationContext, AggregationInput, AggregationMode, ClaimFacts
from app.verdict.policy import POLICY_V4
from app.verdict.service import VerdictService

FROZEN = json.loads(gzip.decompress(
    Path(__file__).with_name("fixtures").joinpath("validated_position_frozen.json.gz").read_bytes()))
EXPECTED = {"smoking85": "not_enough_evidence", "inverse_smoking": "contradicted",
            "sunscreen": "supported", "vitamin_c": "contradicted"}


def saved(case, *, variant=False):
    row = deepcopy(FROZEN[case])
    source = row["variants"][0] if variant else row
    judge = JudgeRun.model_validate_json(json.dumps(source["judge"]))
    pack = EvidencePack.model_validate(row["pack"])
    response = JointResponse23.model_validate_json(json.dumps(
        source["validation_result"]["relation_validation"]["joint_response"]))
    return judge, pack, response


def position_contract(judge, pack, *, advisory="saved"):
    prepared = prepare_compact25(judge.evidence_pack_id, pack)
    raw = json.loads(judge.response_json["raw_model_content"])
    if advisory is None:
        raw.pop("label", None)
    elif advisory != "saved":
        raw["label"] = advisory
    content = json.dumps(raw)
    decision = materialize_content(content, prepared.input_snapshot_json)
    return judge.model_copy(update={
        "decision": decision,
        "response_json": {**decision.model_dump(mode="json"), "raw_model_content": content},
        "input_snapshot_version": prepared.input_snapshot_version,
        "input_snapshot_hash": prepared.input_snapshot_hash,
        "input_snapshot_json": prepared.input_snapshot_json,
        "prompt_version": prepared.prompt_version, "prompt_hash": prepared.prompt_hash,
    })


class SavedChecker:
    provider = "paratera"
    model = "ERNIE-4.5-Turbo-128K"

    def __init__(self, response):
        self.response = response
        self.calls = 0

    async def assess_joint23(self, prepared):
        self.calls += 1
        return self.response


def validate(judge, pack, response):
    checker = SavedChecker(response)
    audit = asyncio.run(validate_joint24(judge, pack, checker))
    assert checker.calls == 1
    return audit


@pytest.mark.parametrize("case", EXPECTED)
@pytest.mark.parametrize("proposal", [None, "supported", "contradicted", "not_enough_evidence",
                                    "conflicting_evidence"])
def test_four_saved_cases_position_is_independent_of_advisory_label(case, proposal):
    old, pack, response = saved(case)
    assert frozen_response_matches24(old, pack)
    before = old.model_dump(mode="json")
    judge = position_contract(old, pack, advisory=proposal)
    assert (judge.input_snapshot_json["source_quantity_catalog"] ==
            old.input_snapshot_json["source_quantity_catalog"])
    assert frozen_response_matches25(judge, pack)
    assert judge.decision.label is None
    assert judge.decision.advisory_label == proposal
    audit = validate(judge, pack, response)
    assert audit.result.validated_evidence_position == EXPECTED[case]
    assert audit.status == "validated"
    assert audit_matches25(judge, audit, pack, "standard")
    assert old.model_dump(mode="json") == before  # No historical mutation/backfill.


def test_wrong_glm_contradiction_becomes_validated_support():
    old, pack, response = saved("sunscreen", variant=True)
    assert old.decision.label == "contradicted"
    audit = validate(position_contract(old, pack), pack, response)
    assert audit.result.validated_evidence_position == "supported"


def test_randomized_direct_result_does_not_depend_on_strong_strength():
    old, pack, response = saved("sunscreen")
    judge = position_contract(old, pack)
    response = response.model_copy(update={"assessments": (
        response.assessments[0].model_copy(update={"strength": "supporting"}),
        *response.assessments[1:],
    )})
    audit = validate(judge, pack, response)
    assert audit.result.validated_evidence_position == "supported"
    qualification = audit.result.conclusion_qualification
    assert qualification["design_materiality_statement_ids"] == ["S1"]
    assert "CAUSAL_DESIGN_INSUFFICIENT" not in qualification["output"]["reason_codes"]
    # Raw validator axes remain exact; backend promotion has its own audit.
    assert audit.result.relation_validation["joint_response"]["assessments"][0][
        "strength"] == "supporting"


def test_weak_randomized_result_reports_materiality_gap_not_design_gap():
    old, pack, response = saved("sunscreen")
    judge = position_contract(old, pack)
    axes = tuple(a.model_copy(update={"strength": "weak"}) for a in response.assessments)
    audit = validate(judge, pack, response.model_copy(update={"assessments": axes}))
    assert audit.result.validated_evidence_position == "not_enough_evidence"
    assert "CAUSAL_DESIGN_INSUFFICIENT" not in audit.result.conclusion_qualification[
        "output"]["reason_codes"]


def test_imprecise_nulls_are_not_material_opposition_and_narrow_benefit_not_conflict():
    for case in ("sunscreen", "vitamin_c"):
        old, pack, response = saved(case)
        audit = validate(position_contract(old, pack), pack, response)
        relations = {r["statement_id"]: r for r in audit.result.conclusion_qualification[
            "guarded_relations"]}
        for axis in response.assessments:
            if axis.finding_basis == "imprecise_null":
                assert relations[axis.statement_id]["relation"] == "insufficient"
        assert audit.result.validated_evidence_position == EXPECTED[case]


def test_strong_narrow_population_benefit_does_not_erase_general_population_review():
    old, pack, response = saved("vitamin_c")
    response = response.model_copy(update={"assessments": (
        *response.assessments[:-1], response.assessments[-1].model_copy(update={
            "direction": "supports_claim", "strength": "strong"}),
    )})
    audit = validate(position_contract(old, pack), pack, response)
    assert audit.result.validated_evidence_position == "contradicted"
    assert audit.result.conclusion_qualification["guarded_relations"][-1][
        "relation"] == "insufficient"


def test_model_conclusion_cannot_hide_a_validated_material_finding():
    old, pack, response = saved("sunscreen")
    judge = position_contract(old, pack)
    raw = json.loads(judge.response_json["raw_model_content"])
    raw["conclusion"]["based_on_statement_ids"] = ["S5"]
    content = json.dumps(raw)
    decision = materialize_content(content, judge.input_snapshot_json)
    judge = judge.model_copy(update={"decision": decision, "response_json": {
        **decision.model_dump(mode="json"), "raw_model_content": content}})
    audit = validate(judge, pack, response)
    assert audit.result.validated_evidence_position == "supported"
    assert audit.result.conclusion_qualification["output"]["decisive_statement_ids"] == ["S1"]


@pytest.mark.parametrize("failure", ["not_established_by_sources", "unable_to_assess"])
def test_source_validation_failure_is_unavailable_not_nei(failure):
    old, pack, response = saved("sunscreen")
    response = response.model_copy(update={"attributions": (
        response.attributions[0].model_copy(update={"status": StatementAttributionStatus(failure)}),
        *response.attributions[1:],
    )})
    audit = validate(position_contract(old, pack), pack, response)
    assert audit.result.validated_evidence_position is None
    assert audit.status != "validated"


def test_missing_checker_and_transport_or_schema_failure_never_produce_nei():
    old, pack, response = saved("sunscreen")
    judge = position_contract(old, pack)

    class Broken(SavedChecker):
        async def assess_joint23(self, prepared):
            raise ValueError("Invalid saved response schema")

    for checker in (None, Broken(response)):
        audit = asyncio.run(validate_joint24(judge, pack, checker))
        assert audit.result.validated_evidence_position is None
        assert audit.status != "validated"


def test_bad_quantity_reference_is_preflight_failure_not_nei():
    old, pack, response = saved("sunscreen")
    judge = position_contract(old, pack)
    bad = judge.decision.statements[0].model_copy(update={"source_quantity_ids": ("E999.U1.Q1",)})
    judge = judge.model_copy(update={"decision": judge.decision.model_copy(update={
        "statements": (bad, *judge.decision.statements[1:])})})
    checker = SavedChecker(response)
    audit = asyncio.run(validate_joint24(judge, pack, checker))
    assert checker.calls == 0
    assert audit.result.validated_evidence_position is None
    assert audit.status == "invalid"


def test_new_contract_omits_label_requirement_old_invalid_labels_still_rejected():
    assert "label" not in JudgeContent25.model_json_schema()["required"]
    old, pack, _ = saved("sunscreen")
    raw = json.loads(old.response_json["raw_model_content"])
    raw["label"] = "conflicting_evidence"
    with pytest.raises(ValueError):
        JudgeContent24.model_validate_json(json.dumps(raw))
    with pytest.raises(ValueError):
        materialize_content(json.dumps(raw), old.input_snapshot_json)


def test_normal_development_contract_and_provider_schema_have_no_voting_label(monkeypatch):
    old, pack, _ = saved("sunscreen")
    raw = json.loads(old.response_json["raw_model_content"])
    raw.pop("label")
    content = json.dumps(raw)

    class Provider:
        async def evaluate(self, slot, prepared):
            assert prepared.input_snapshot_version == "judge-input-2.5"
            return ProviderResponse(content=content)

    slot = JudgeSlot(slot=1, provider="paratera", model=old.model, model_family=old.model_family,
                     base_url="https://fixture.invalid/v1")
    service = JudgeService({"paratera": Provider()}, axes_development=True)
    runs, summary = asyncio.run(service.run(old.evidence_pack_id, pack, (slot,),
                                           app_env="development"))
    run = runs[0]
    assert summary.successful_judges == 1
    assert not any(summary.label_counts.values())
    assert run.outcome_status == "succeeded"
    assert run.decision.schema_version == "2.5"
    assert run.decision.label is None
    assert frozen_response_matches25(run, pack)

    def respond(request):
        schema = json.loads(request.content)["response_format"]["json_schema"]
        assert schema["strict"] is True
        assert "label" not in schema["schema"]["properties"]
        assert "label" not in schema["schema"]["required"]
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = httpx.AsyncClient
    monkeypatch.setattr("app.adapters.judge.httpx.AsyncClient",
                        lambda **kw: client(transport=httpx.MockTransport(respond), **kw))
    asyncio.run(OpenAICompatibleJudgeProvider(1).evaluate(slot, prepare_compact25(
        old.evidence_pack_id, pack)))


def test_observational_design_cannot_borrow_a_parent_rct_label():
    old, pack, response = saved("sunscreen")
    judge = position_contract(old, pack)
    data = qualification_input24(judge, pack, response, "standard")
    finding = data.base.findings[0]
    facts = tuple(f.model_copy(update={"analysis_design": "observational",
                                      "exposure_assignment": "observed"})
                  for f in finding.evidence_design_facts)
    data = data.model_copy(update={"base": data.base.model_copy(update={"findings": (
        finding.model_copy(update={"evidence_design_facts": facts}), *data.base.findings[1:],
    )})})
    output = derive_position(data)
    assert output.validated_evidence_position == "not_enough_evidence"
    assert output.output.reason_codes == ("CAUSAL_DESIGN_INSUFFICIENT",)


def test_both_eligible_material_directions_produce_audited_conflict():
    old, pack, response = saved("vitamin_c")
    judge = position_contract(old, pack)
    # An adversarial axes control over the same saved review; no new clinical case.
    response = response.model_copy(update={"assessments": (
        response.assessments[0].model_copy(update={"direction": "supports_claim"}),
        *response.assessments[1:],
    )})
    data = qualification_input24(judge, pack, response, "standard")
    # In the actual saved pack S1 has a deterministic mismatch, so it cannot
    # supply a vote. Explicitly make this a material-conflict guard control.
    data = data.model_copy(update={"base": data.base.model_copy(update={"findings": (
        data.base.findings[0].model_copy(update={"deterministic_scopes": ("aligned",)}),
        *data.base.findings[1:],
    )})})
    result = derive_position(data)
    assert result.validated_evidence_position == "not_enough_evidence"
    assert result.output.reason_codes == ("CONFLICTING_FINDINGS",)


@pytest.mark.parametrize("case,omit_material_dependency", [
    *( (case, False) for case in EXPECTED), ("sunscreen", True),
])
def test_aggregation_report_reconstruction_and_tamper_rejection(case, omit_material_dependency):
    old, pack, response = saved(case)
    judge = position_contract(old, pack, advisory="contradicted")
    if omit_material_dependency:
        raw = json.loads(judge.response_json["raw_model_content"])
        raw["conclusion"]["based_on_statement_ids"] = ["S5"]
        content = json.dumps(raw)
        decision = materialize_content(content, judge.input_snapshot_json)
        judge = judge.model_copy(update={"decision": decision, "response_json": {
            **decision.model_dump(mode="json"), "raw_model_content": content}})
    judges = (judge, judge.model_copy(update={"judge_run_id": uuid4(),
                                            "slot": 3 if judge.slot == 2 else 2,
                                            "model_family": "offline-second-family"}))
    audits = tuple(validate(j, pack, response) for j in judges)
    request = AggregationInput(claim_id=pack.claim_id, evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=pack.snapshot_hash, judge_run_ids=tuple(j.judge_run_id for j in judges),
        judge_validation_run_ids=tuple(a.id for a in audits),
        mode=AggregationMode.FIXTURE_OR_EVALUATION, policy_version=POLICY_V4.version)
    context = AggregationContext(claim=ClaimFacts(claim_id=pack.claim_id, risk_class="standard",
        normalization_status="normalized"), pack=pack, stored_pack_hash=pack.snapshot_hash,
        retrieval_status="ok", judges=judges, validations=audits)
    service = VerdictService(POLICY_V4)
    verdict = service.aggregate(request, context)
    assert verdict.verdict == EXPECTED[case] and verdict.qualified_judges == 2
    assert all(q.label == EXPECTED[case] for q in verdict.judge_qualifications)
    report = build_report(uuid4(), verdict, pack, judges, audits)
    assert report.verdict == EXPECTED[case]
    assert report.verdict_explanation is not None
    for field in ("validated_evidence_position", "conclusion_qualification"):
        altered = (JudgeLabel.SUPPORTED if EXPECTED[case] != "supported"
                   else JudgeLabel.CONTRADICTED)
        altered = (altered if field == "validated_evidence_position" else
                   {**audits[0].result.conclusion_qualification,
                    "validated_evidence_position": altered})
        bad = audits[0].model_copy(update={"result": audits[0].result.model_copy(
            update={field: altered})})
        assert not audit_matches25(judge, bad, pack, "standard")
        rejected = service.aggregate(request, context.model_copy(update={
            "validations": (bad, audits[1])}))
        assert rejected.verdict == "unable_to_verify_reliably"
    production = service.aggregate(request.model_copy(update={"mode": AggregationMode.PRODUCTION}),
                                   context)
    assert production.verdict == "unable_to_verify_reliably"
    assert not production.production_qualified
