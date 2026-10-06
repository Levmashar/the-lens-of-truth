"""Offline conditional V2.4 contracts; no medical oracle or model traffic."""

import asyncio
import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest

from app.adapters.judge import OpenAICompatibleJudgeProvider
from app.evaluation.slice41_cases import CASES, annotated_response, probe_judge
from app.judging.compact23 import prepare_compact23
from app.judging.compact24 import frozen_response_matches24, prepare_compact24
from app.judging.models import JudgeSlot, ProviderResponse, parse_stored_decision
from app.judging.prompt import input_snapshot_hash, prepare_judge_input
from app.judging.service import DecisionFailure, JudgeService, parse_provider_decision
from app.judging.source_quantities import catalog_items, derive_catalog
from app.judging.source_units import JudgeContent24, materialize_content
from app.pipeline.numeric_effect import numeric_effect
from app.retrieval.evidence_pack import canonical_pack_bytes
from app.validation.audit23 import audit_matches23
from app.validation.audit24 import audit_matches24
from app.validation.axes import mapped_relations
from app.validation.joint24 import prepare_joint24, validate_joint24
from app.validation.models import IssueCode, StatementAttributionStatus
from app.validation.numeric24 import numeric_findings24, numeric_issues24
from app.validation.service import ValidationService
from app.verdict.models import AggregationContext, AggregationInput, AggregationMode, ClaimFacts
from app.verdict.policy import POLICY_V4
from app.verdict.service import VerdictService, _validation_failure

SMOKING = next(c for c in CASES if c.id == "smoking-positive")
SOURCE = ("The risk of lung cancer development is 20-40 times higher in lifelong smokers "
          "compared to non-smokers. Tobacco use is the main cause of 90% of male and 79% of "
          "female lung cancers. Based on solid evidence, smoking causes lung cancer.")


def structured_fixture(*, source=SOURCE, claim="Smoking increases lung cancer risk by 85%.",
                       selected=None, prose="Smoking is associated with higher lung cancer risk.",
                       scope="aligned", scope_basis="same_question", label="not_enough_evidence",
                       attribution="supported_by_sources"):
    case = replace(SMOKING, source=source, claim=claim, label=label, scope=scope,
                   scope_basis=scope_basis, finding=prose, attribution=attribution)
    judge, pack = probe_judge(case)
    pico = pack.claim_snapshot.pico.model_copy(update={"numeric_effect": numeric_effect(claim)})
    snapshot = pack.claim_snapshot.model_copy(update={"pico": pico})
    digest = hashlib.sha256(canonical_pack_bytes(
        snapshot, pack.query_plan, pack.documents, pack.passages,
        pack.selected_evidence_ids, pack_version=pack.evidence_pack_version,
    )).hexdigest()
    pack = pack.model_copy(update={"claim_snapshot": snapshot, "snapshot_hash": digest})
    prepared = prepare_compact24(judge.evidence_pack_id, pack)
    quantities = catalog_items(prepared.input_snapshot_json)
    ids = list(quantities) if selected is None else selected
    raw = json.loads(judge.response_json["raw_model_content"])
    statement = raw["statements"][0]
    statement.pop("numeric_details")
    statement.update({"source_quantity_ids": ids, "text": prose, "qualitative_finding": prose})
    raw["conclusion"].update({"justification": "S1 does not establish 85%.",
                               "qualitative_justification": "No support for the exact 85%."})
    return with_content(judge.model_copy(update={
        "evidence_pack_hash": digest, "input_snapshot_version": prepared.input_snapshot_version,
        "input_snapshot_json": prepared.input_snapshot_json,
        "input_snapshot_hash": prepared.input_snapshot_hash,
        "prompt_version": prepared.prompt_version, "prompt_hash": prepared.prompt_hash,
    }), raw), pack, annotated_response(case)


def with_content(judge, raw):
    content = json.dumps(raw)
    decision = materialize_content(content, judge.input_snapshot_json)
    return judge.model_copy(update={"decision": decision, "response_json": {
        **decision.model_dump(mode="json"), "raw_model_content": content,
    }})


class OfflineChecker:
    provider = model = "fixture"

    def __init__(self, response):
        self.response, self.calls = response, 0

    async def assess_joint23(self, prepared):
        self.calls += 1
        return self.response


def validate(judge, pack, response):
    checker = OfflineChecker(response)
    audit = asyncio.run(validate_joint24(judge, pack, checker))
    return audit, checker


def test_catalog_stable_ids_source_literals_hash_and_pack_immutability():
    judge, pack, _ = structured_fixture()
    before = pack.model_dump(mode="json")
    frozen = judge.input_snapshot_json
    assert frozen["source_quantity_catalog"]["version"] == "source-quantity-catalog-1.0"
    assert derive_catalog(frozen["source_units"]) == frozen["source_quantity_catalog"]
    items = list(catalog_items(frozen).values())
    assert [q.quantity_id for q in items] == ["E1.U1.Q1", "E1.U1.Q2", "E1.U1.Q3"]
    assert items[0].values == ("20", "40") and items[0].measure == "fold_change"
    assert items[0].normalization_reason == "literal_times_higher_no_arithmetic_convention"
    assert items[0].unit == "risk_multiple"
    assert [q.binding for q in items[1:]] == ["male", "female"]
    for q in items:
        assert SOURCE[q.start:q.end] == q.literal
        assert q.evidence_id == "E1" and q.source_unit_id == "E1.U1"
    again = prepare_compact24(judge.evidence_pack_id, pack)
    assert again.input_snapshot_hash == judge.input_snapshot_hash
    changed = deepcopy(frozen)
    changed["source_quantity_catalog"]["items"][0]["values"] = ["21", "40"]
    assert input_snapshot_hash(changed) != judge.input_snapshot_hash
    with pytest.raises(ValueError, match="catalog identity"):
        catalog_items(changed)
    assert pack.model_dump(mode="json") == before


@pytest.mark.parametrize("phrase", ["20-40 times higher", "20-40x", "many-fold higher",
                                   "far above the claimed magnitude", "far above the claimed 85%",
                                   "does not establish 85%", "no support for the exact 85%",
                                   "risk 123456%, RR 999, OR 0.001"])
def test_smoking_metamorphic_all_numeric_prose_fields_are_inert(phrase, monkeypatch):
    judge, pack, response = structured_fixture(selected=["E1.U1.Q1"])
    baseline, _ = validate(judge, pack, response)
    raw = json.loads(judge.response_json["raw_model_content"])
    raw["statements"][0].update({"text": f"The source describes {phrase}.",
                                  "qualitative_finding": f"The source describes {phrase}."})
    raw["conclusion"].update({"justification": f"S1 describes {phrase}.",
                              "qualitative_justification": f"S1 describes {phrase}."})
    changed = with_content(judge, raw)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("V2.4 must not call judge-prose numeric gates")

    monkeypatch.setattr("app.validation.numeric23.numeric_issues23", forbidden)
    monkeypatch.setattr("app.validation.numeric23.numeric_findings23", forbidden)
    monkeypatch.setattr("app.validation.numeric23.numeric_occurrences23", forbidden)
    monkeypatch.setattr("app.validation.relation_flow.claim_magnitude_alignment", forbidden)
    monkeypatch.setattr("app.validation.v2.compare_assertion_numbers", forbidden)
    audit, checker = validate(changed, pack, response)
    assert checker.calls == 1
    assert audit.result.numeric_findings == baseline.result.numeric_findings
    assert audit.result.conclusion_qualification == baseline.result.conclusion_qualification
    assert audit.result.targeted_issues == ()
    assert audit.result.numeric_occurrences is None
    assert len(audit.result.numeric_findings) == 1  # Luna repetition creates no extra diagnostic.
    assert audit_matches24(changed, audit, pack, "standard")


@pytest.mark.parametrize("source,status,effect", [
    ("Smoking raises lung cancer risk; RR 1.85.", "aligned", "supports_magnitude"),
    ("Smoking raises lung cancer risk; RR 2.", "aligned", "opposes_magnitude"),
    ("Smoking raises lung cancer risk; OR 1.85.", "different_measure", "noncomparable"),
    ("Smoking raises lung cancer risk; HR 1.85.", "different_measure", "noncomparable"),
    ("Smoking raises lung cancer risk by 85 percentage points.", "different_measure",
     "noncomparable"),
    ("90% of lung cancers are attributable to tobacco.", "different_measure", "noncomparable"),
    ("Lung cancer risk is 20-40 times higher with smoking.", "aligned", "unresolved"),
    ("RR 1.85 in lifelong smokers compared to non-smokers.", "compatible_but_narrower",
     "noncomparable"),
    ("RR 1.85 in heavy smokers compared to non-smokers.", "compatible_but_narrower",
     "noncomparable"),
])
def test_typed_comparison_and_restrictions_reach_semantics(source, status, effect):
    judge, pack, response = structured_fixture(source=source)
    audit, checker = validate(judge, pack, response)
    assert checker.calls == 1 and audit.error_category is None
    assert not audit.result.targeted_issues
    rows = audit.result.numeric_findings
    assert len(rows) == 1
    assert rows[0]["fidelity"]["status"] == "verified"
    assert rows[0]["comparability"]["status"] == status
    assert rows[0]["numeric_effect"] == effect
    eligible = audit.result.conclusion_qualification["input"]["magnitude_eligible"]["S1"]
    assert eligible == (effect in {"supports_magnitude", "opposes_magnitude"})


@pytest.mark.parametrize("scope,basis,expected", [
    ("compatible_but_narrower", "population", "compatible_but_narrower"),
    ("compatible_but_narrower", "dose", "compatible_but_narrower"),
    ("incompatible", "active_alternative", "different_comparator"),
    ("incompatible", "endpoint", "different_endpoint"),
    ("uncertain", "uncertain", "uncertain"),
])
def test_scope_is_applied_only_after_checker(scope, basis, expected):
    judge, pack, response = structured_fixture(source="RR 1.85 for lung cancer risk.",
                                              scope=scope, scope_basis=basis)
    pre = numeric_findings24(judge.decision, pack, judge.input_snapshot_json)
    assert pre[0]["comparability"]["reason"] == "semantic_scope_pending"
    assert not pre[0]["semantic_scope_checked"]
    audit, checker = validate(judge, pack, response)
    assert checker.calls == 1
    assert audit.result.numeric_findings[0]["comparability"]["status"] == expected
    assert audit.result.numeric_findings[0]["semantic_scope_checked"]


@pytest.mark.parametrize("claim,label,qualified", [
    ("Smoking causes lung cancer.", "supported", True),
    ("Smoking increases lung cancer risk by 85%.", "supported", False),
    ("Smoking increases lung cancer risk by 85%.", "contradicted", False),
    ("Smoking increases lung cancer risk by 85%.", "not_enough_evidence", True),
])
def test_zero_refs_can_establish_direction_but_never_exact_magnitude(claim, label, qualified):
    judge, pack, response = structured_fixture(selected=[], claim=claim, label=label)
    if label == "contradicted":
        response = response.model_copy(update={"assessments": (
            response.assessments[0].model_copy(update={"direction": "opposes_claim"}),)})
    audit, checker = validate(judge, pack, response)
    assert checker.calls == 1 and bool(audit.status == "validated") == qualified
    assert audit.result.numeric_findings == ()
    assert judge.decision.label == label
    assert not audit.result.targeted_issues


def test_multiple_paf_refs_and_luna_duplicate_regression():
    judge, pack, response = structured_fixture()
    raw = json.loads(judge.response_json["raw_model_content"])
    for field in ("text", "qualitative_finding"):
        raw["statements"][0][field] = "20-40x risk elevation; 90% male and 79% female PAF."
    for field in ("justification", "qualitative_justification"):
        raw["conclusion"][field] = "S1 reports 20-40 times higher, 20-40x, 90%/79%, not 85%."
    changed = with_content(judge, raw)
    audit, checker = validate(changed, pack, response)
    assert checker.calls == 1
    assert len(audit.result.numeric_findings) == 3
    assert len({n["source_quantity_id"] for n in audit.result.numeric_findings}) == 3
    assert all(n["fidelity"]["status"] == "verified" for n in audit.result.numeric_findings)
    assert all(n["comparability"]["status"] == "different_measure"
               for n in audit.result.numeric_findings[1:])


@pytest.mark.parametrize("bad_id", ["E999.U1.Q1", "E1.U1.Q99", "E1.U2.Q1"])
def test_unknown_quantity_ids_rejected_at_schema_materialization_and_gate(bad_id):
    judge, pack, response = structured_fixture()
    raw = json.loads(judge.response_json["raw_model_content"])
    raw["statements"][0]["source_quantity_ids"] = [bad_id]
    with pytest.raises(DecisionFailure, match="invalid_source_quantity"):
        parse_provider_decision(json.dumps(raw), ("E1",), snapshot=judge.input_snapshot_json)
    bad = judge.model_copy(update={"decision": judge.decision.model_copy(update={
        "statements": (judge.decision.statements[0].model_copy(update={
            "source_quantity_ids": (bad_id,),
        }),),
    })})
    audit, checker = validate(bad, pack, response)
    assert checker.calls == 0 and audit.error_category == "reference_preflight_failure"
    assert IssueCode.SOURCE_QUANTITY_REFERENCE_INVALID in audit.result.fatal_issue_codes


def test_quantity_from_uncited_unit_is_wrong_owner():
    judge, _, _ = structured_fixture()
    snapshot = deepcopy(judge.input_snapshot_json)
    second = {**snapshot["source_units"][0], "unit_id": "E2.U1", "evidence_id": "E2"}
    snapshot["source_units"].append(second)
    snapshot["source_quantity_catalog"] = derive_catalog(snapshot["source_units"])
    raw = json.loads(judge.response_json["raw_model_content"])
    raw["statements"][0]["source_quantity_ids"] = ["E2.U1.Q1"]
    with pytest.raises(ValueError, match="uncited unit"):
        materialize_content(json.dumps(raw), snapshot)
    bad = judge.decision.model_copy(update={"statements": (
        judge.decision.statements[0].model_copy(update={"source_quantity_ids": ("E2.U1.Q1",)}),)})
    assert numeric_issues24(bad, snapshot)[0].issue_code == "SOURCE_QUANTITY_REFERENCE_INVALID"


@pytest.mark.parametrize("mutation", ["value", "literal", "owner", "offset", "version",
                                      "source_text", "unit_hash"])
@pytest.mark.parametrize("rehash", [False, True])
def test_frozen_snapshot_tamper_skips_checker_even_with_recomputed_hash(mutation, rehash):
    judge, pack, response = structured_fixture()
    frozen = deepcopy(judge.input_snapshot_json)
    quantity = frozen["source_quantity_catalog"]["items"][0]
    if mutation == "source_text":
        frozen["source_units"][0]["text"] += "RR 99."
    elif mutation == "unit_hash":
        frozen["source_units"][0]["passage_sha256"] = "f" * 64
    elif mutation == "version":
        frozen["source_quantity_catalog"]["version"] = "source-quantity-catalog-9.0"
    else:
        field, value = {"value": ("values", ["21", "40"]), "literal": ("literal", "RR 99"),
                        "owner": ("source_unit_id", "E9.U1"), "offset": ("start", 1)}[mutation]
        quantity[field] = value
    bad = judge.model_copy(update={"input_snapshot_json": frozen,
        "input_snapshot_hash": input_snapshot_hash(frozen) if rehash
        else judge.input_snapshot_hash})
    audit, checker = validate(bad, pack, response)
    assert checker.calls == 0 and audit.status == "invalid"
    assert audit.result.semantic_validation["state"] == "skipped_due_to_reference_preflight"


@pytest.mark.parametrize("mutation", ["raw", "canonical", "prompt", "normalization"])
def test_response_and_provenance_tamper_fail_closed(mutation):
    judge, pack, response = structured_fixture()
    updates = {}
    raw = deepcopy(judge.response_json)
    if mutation == "raw":
        data = json.loads(raw["raw_model_content"])
        data["statements"][0]["source_quantity_ids"] = ["E1.U1.Q2"]
        raw["raw_model_content"] = json.dumps(data)
    elif mutation == "canonical":
        raw["statements"][0]["text"] = "Tampered stored response."
    elif mutation == "prompt":
        updates["prompt_hash"] = "f" * 64
    else:
        raw["source_unit_id_normalizations"] = [{"statement_id": "S1", "from": "E9"}]
    bad = judge.model_copy(update={**updates, "response_json": raw})
    audit, checker = validate(bad, pack, response)
    assert checker.calls == 0 and audit.error_category == "reference_preflight_failure"


def test_semantic_attribution_omission_and_unavailability_remain_required():
    judge, pack, response = structured_fixture(selected=[])
    bad = response.model_copy(update={"attributions": (
        response.attributions[0].model_copy(update={
            "status": StatementAttributionStatus.NOT_ESTABLISHED_BY_SOURCES}),)})
    audit, checker = validate(judge, pack, bad)
    assert checker.calls == 1 and audit.status == "invalid"
    assert IssueCode.STATEMENT_ATTRIBUTION_FAILED in audit.result.fatal_issue_codes
    missing = response.model_copy(update={"missing_material_evidence": True})
    audit, checker = validate(judge, pack, missing)
    assert checker.calls == 1 and audit.status != "validated"
    assert audit.error_category == "missing_material_evidence"
    unavailable = asyncio.run(validate_joint24(judge, pack, None))
    assert unavailable.status != "validated" and unavailable.attempt_count == 0


def test_audit_reconstructs_through_jsonb_and_rejects_numeric_and_qualifier_tamper():
    judge, pack, response = structured_fixture()
    audit, _ = validate(judge, pack, response)
    assert audit_matches24(judge, audit, pack, "standard")
    restored = audit.__class__.model_validate_json(audit.model_dump_json())
    assert audit_matches24(judge, restored, pack, "standard")
    assert parse_stored_decision(judge.decision.model_dump(mode="json")) == judge.decision
    for field in ("numeric_findings", "conclusion_qualification", "relation_validation"):
        value = deepcopy(getattr(audit.result, field))
        if field == "numeric_findings":
            value[0]["fidelity"]["source"]["values"] = ["999"]
        elif field == "conclusion_qualification":
            value["input"]["magnitude_eligible"]["S1"] = True
        else:
            value["input_hash"] = "f" * 64
        bad = audit.model_copy(update={"result": audit.result.model_copy(update={field: value})})
        assert not audit_matches24(judge, bad, pack, "standard")


def test_magnitude_gate_and_verdict_report_reconstruction():
    judge, pack, response = structured_fixture()
    audit, _ = validate(judge, pack, response)
    from app.report.builder import build_report
    from app.validation.axes import AxesQualificationAudit

    qualified = AxesQualificationAudit.model_validate(audit.result.conclusion_qualification)
    assert not qualified.input.magnitude_eligible["S1"]
    assert mapped_relations(qualified.input)[0].relation == "insufficient"
    assert _validation_failure(judge, audit, POLICY_V4, evaluation_mode=True) is None
    assert _validation_failure(judge, audit, POLICY_V4, evaluation_mode=False) is not None
    judges = (judge, judge.model_copy(update={"judge_run_id": uuid4(), "slot": 2,
                                            "model_family": "second-fixture"}))
    audits = tuple(validate(j, pack, response)[0] for j in judges)
    request = AggregationInput(
        claim_id=pack.claim_id, evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=pack.snapshot_hash, judge_run_ids=tuple(j.judge_run_id for j in judges),
        judge_validation_run_ids=tuple(a.id for a in audits),
        mode=AggregationMode.FIXTURE_OR_EVALUATION, policy_version=POLICY_V4.version,
    )
    context = AggregationContext(
        claim=ClaimFacts(claim_id=pack.claim_id, risk_class="standard",
                         normalization_status="normalized"), pack=pack,
        stored_pack_hash=pack.snapshot_hash, retrieval_status="ok",
        judges=judges, validations=audits,
    )
    verdict = VerdictService(POLICY_V4).aggregate(request, context)
    assert verdict.verdict == "not_enough_evidence"
    report = build_report(uuid4(), verdict, pack, judges, audits)
    assert report.verdict_explanation is not None
    assert "85%" in report.verdict_explanation.summary
    bad = audits[0].model_copy(update={"prompt_hash": "f" * 64})
    refused = VerdictService(POLICY_V4).aggregate(request, context.model_copy(update={
        "validations": (bad, audits[1]),
    }))
    assert refused.verdict == "unable_to_verify_reliably"


def test_historical23_reconstruction_and_shapes_are_unchanged():
    from app.validation.joint23 import validate_joint23
    from tests.test_numeric_fidelity_comparability import pattern
    from tests.test_reliability_slice4_1 import FixtureValidator

    old, pack, response = pattern("luna")
    audit = asyncio.run(validate_joint23(old, pack, OfflineChecker(response)))
    assert audit_matches23(old, audit, pack, "standard")
    assert "source_quantity_catalog" not in old.input_snapshot_json
    assert "source_quantity_ids" not in old.decision.statements[0].model_dump(mode="json")
    assert "numeric_details" in old.decision.statements[0].model_dump(mode="json")
    before = prepare_compact23(old.evidence_pack_id, pack)
    prepare_compact24(old.evidence_pack_id, pack)
    after = prepare_compact23(old.evidence_pack_id, pack)
    assert before == after
    bad_case = next(c for c in CASES if c.id == "numeric-distortion")
    old_bad, pack_bad = probe_judge(bad_case)
    checker = FixtureValidator(bad_case)
    failed = asyncio.run(validate_joint23(old_bad, pack_bad, checker))
    assert checker.calls == 0 and failed.status != "validated"


def test_schema_excludes_numeric_values_details_and_conclusion_refs():
    judge, _, _ = structured_fixture()
    schema = JudgeContent24.model_json_schema()
    properties = schema["$defs"]["UnitStatement24"]["properties"]
    assert "source_quantity_ids" in properties and "numeric_details" not in properties
    raw = json.loads(judge.response_json["raw_model_content"])
    for field in ("numeric_details", "values", "quantity_id"):
        bad = deepcopy(raw)
        bad["statements"][0][field] = []
        with pytest.raises(ValueError):
            materialize_content(json.dumps(bad), judge.input_snapshot_json)
    raw["conclusion"]["source_quantity_ids"] = ["E1.U1.Q1"]
    with pytest.raises(ValueError):
        materialize_content(json.dumps(raw), judge.input_snapshot_json)


def test_development_service_and_validation_routing_v3_stays_probe_only():
    judge, pack, response = structured_fixture()
    prepared_checker = prepare_joint24(judge, pack, "fixture")
    payload = json.loads(prepared_checker.user_prompt.split("\n", 1)[1])
    assert payload["candidate_statements"][0]["source_quantity_ids"] == list(
        judge.decision.statements[0].source_quantity_ids)
    assert payload["candidate_statements"][0]["source_quantities"] == list(
        judge.input_snapshot_json["source_quantity_catalog"]["items"])
    raw = judge.response_json["raw_model_content"]

    class FakeProvider:
        async def evaluate(self, slot, prepared):
            assert prepared.input_snapshot_version == "judge-input-2.4"
            return ProviderResponse(content=raw)

    slot = JudgeSlot(slot=1, provider="fixture", model="unchanged-model",
                     model_family="fixture", base_url="https://example.invalid")
    service = JudgeService({"fixture": FakeProvider()}, axes_development=True, axes_contract="2.4")
    run = asyncio.run(service.run(uuid4(), pack, (slot,), app_env="development"))[0][0]
    assert run.decision.schema_version == "2.4" and run.model == slot.model
    assert frozen_response_matches24(run, pack)
    checker = OfflineChecker(response)
    audit = asyncio.run(ValidationService(semantic_validator=checker).run(run, pack))
    assert checker.calls == 1 and audit.validation_version == "judge-validation-2.4"
    with pytest.raises(ValueError, match="development/test only"):
        asyncio.run(service.run(uuid4(), pack, (slot,), app_env="production"))
    production_input = prepare_judge_input(uuid4(), pack)
    assert production_input.input_snapshot_version == "judge-input-2.2"
    from app.judging.v3 import prepare_v3

    probe = prepare_v3(production_input)
    assert probe.input_snapshot_version == "judge-input-3.0"
    assert "source_quantity_catalog" not in production_input.input_snapshot_json


def test_provider_schema_selection_24_is_explicit_and_offline(monkeypatch):
    judge, pack, _ = structured_fixture()
    prepared = prepare_compact24(judge.evidence_pack_id, pack)
    captured = []

    async def post(_client, url, *, headers, json):
        captured.append(json)
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"choices": [{"message": {
            "content": judge.response_json["raw_model_content"]}}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    slot = JudgeSlot(slot=1, provider="openai_compatible", model="unchanged-model",
                     model_family="fixture", base_url="https://example.invalid")
    asyncio.run(OpenAICompatibleJudgeProvider(1).evaluate(slot, prepared))
    schema = captured[0]["response_format"]["json_schema"]["schema"]
    assert "source_quantity_ids" in json.dumps(schema)
    assert "numeric_details" not in json.dumps(schema)


@pytest.mark.parametrize("label", ["supported", "contradicted"])
def test_paf_or_hr_cannot_power_a_magnitude_vote(label):
    for source in ("90% of lung cancers attributable to tobacco.", "OR 1.85.", "HR 1.85."):
        judge, pack, response = structured_fixture(source=source, label=label)
        direction = "supports_claim" if label == "supported" else "opposes_claim"
        response = response.model_copy(update={"assessments": (
            response.assessments[0].model_copy(update={"direction": direction}),)})
        audit, checker = validate(judge, pack, response)
        assert checker.calls == 1 and audit.status != "validated"
        assert audit.error_category is None
        assert judge.decision.label == label
        assert audit.result.numeric_findings[0]["numeric_effect"] == "noncomparable"


@pytest.mark.parametrize("source,claim,effect", [
    ("Risk increases by 85%.", "Smoking increases lung cancer risk by 85%.",
     "supports_magnitude"),
    ("Risk decreases by 85%.", "Smoking increases lung cancer risk by 85%.",
     "opposes_magnitude"),
    ("Risk increases by 5 percentage points.",
     "Smoking increases lung cancer risk by 5 percentage points.", "supports_magnitude"),
    ("Risk increases by 5%.", "Smoking increases lung cancer risk by 5 percentage points.",
     "noncomparable"),
    ("Risk changed from 10% to 20%.", "Smoking increases lung cancer risk by 100%.",
     "supports_magnitude"),
    ("RR 2 for lung cancer risk.", "Smoking doubles lung cancer risk.", "supports_magnitude"),
])
def test_exact_values_direction_explicit_conversions_and_measure_separation(source, claim, effect):
    judge, pack, response = structured_fixture(source=source, claim=claim)
    audit, checker = validate(judge, pack, response)
    assert checker.calls == 1
    assert audit.result.numeric_findings[0]["numeric_effect"] == effect
    if "from" in source:
        assert audit.result.numeric_findings[0]["comparability"]["conversions"] == [
            "relative_change=(exposed-baseline)/baseline*100"]


def test_unknown_source_quantity_and_corrupt_pack_are_operationally_distinct():
    judge, pack, response = structured_fixture(source="Smoking is associated with risk; 2010.")
    audit, checker = validate(judge, pack, response)
    assert checker.calls == 1 and audit.error_category is None
    assert audit.result.numeric_findings[0]["fidelity"]["status"] == "verified"
    assert audit.result.numeric_findings[0]["fidelity"]["source"]["kind"] == "unknown"
    assert audit.result.numeric_findings[0]["numeric_effect"] == "unresolved"
    corrupt = pack.model_copy(update={"snapshot_hash": "f" * 64})
    audit, checker = validate(judge, corrupt, response)
    assert checker.calls == 0 and audit.status == "invalid"
    assert audit.error_category == "reference_preflight_failure"
    assert audit.result.numeric_findings == ()


def test_duplicate_refs_and_missing_field_are_schema_defects():
    judge, _, _ = structured_fixture()
    raw = json.loads(judge.response_json["raw_model_content"])
    raw["statements"][0]["source_quantity_ids"] = ["E1.U1.Q1", "E1.U1.Q1"]
    with pytest.raises(ValueError, match="Duplicate source quantity"):
        materialize_content(json.dumps(raw), judge.input_snapshot_json)
    raw["statements"][0].pop("source_quantity_ids")
    with pytest.raises(ValueError):
        materialize_content(json.dumps(raw), judge.input_snapshot_json)


def test_wrong_numeric_proposition_is_still_subject_to_independent_attribution():
    judge, pack, response = structured_fixture(source="RR 1.85 for lung cancer risk.",
        prose="The source establishes RR 999 for lung cancer risk.", label="supported")
    # Stipulated rejection shows the numeric transport does not bypass semantics.
    response = response.model_copy(update={"attributions": (
        response.attributions[0].model_copy(update={
            "status": StatementAttributionStatus.NOT_ESTABLISHED_BY_SOURCES}),)})
    audit, checker = validate(judge, pack, response)
    assert checker.calls == 1 and audit.status == "invalid"
    assert audit.result.numeric_findings[0]["fidelity"]["status"] == "verified"
    assert IssueCode.STATEMENT_ATTRIBUTION_FAILED in audit.result.fatal_issue_codes


def test_worker_uses_same_joint_checker_for24(monkeypatch):
    from unittest.mock import MagicMock

    from app.core.config import Settings
    from app.orchestration.worker import build_orchestrator

    judge, pack, response = structured_fixture()
    checker = OfflineChecker(response)
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.return_value.risk_class = "standard"
    monkeypatch.setattr("app.orchestration.worker.SessionLocal", lambda: session)
    monkeypatch.setattr("app.orchestration.worker.development_entailment_validator",
                        lambda *_args: None)
    monkeypatch.setattr("app.orchestration.worker.configured_development_validator",
                        lambda *_args, **_kwargs: checker)
    worker = build_orchestrator(Settings(_env_file=None, app_env="development"))
    audit = asyncio.run(worker.validate(judge, pack))
    assert checker.calls == 1 and audit.validation_version == "judge-validation-2.4"


def test_debug24_exposes_quantity_identity_and_retains_semantic_axes():
    from unittest.mock import Mock

    from sqlalchemy.orm import Session

    from app.api.routes.analyses import _debug_judge_runs
    from app.models.analysis_run import ClaimAnalysisRunRecord
    from app.models.judge_run import JudgeRunRecord
    from app.models.judge_validation_run import JudgeValidationRunRecord

    judge, pack, response = structured_fixture()
    audit, _ = validate(judge, pack, response)
    row = ClaimAnalysisRunRecord(claim_id=pack.claim_id,
        judge_run_ids=[str(judge.judge_run_id)], validation_run_ids=[str(audit.id)])
    stored_judge = JudgeRunRecord(
        id=judge.judge_run_id, claim_id=pack.claim_id, slot=1, provider=judge.provider,
        model=judge.model, model_family=judge.model_family, outcome_status="succeeded",
        attempt_count=1, latency_ms=0, decision_json=judge.decision.model_dump(mode="json"),
        response_json=judge.response_json,
    )
    stored_audit = JudgeValidationRunRecord(
        id=audit.id, judge_run_id=judge.judge_run_id, status=audit.status.value,
        error_category=audit.error_category, result_json=audit.result.model_dump(mode="json"),
    )
    session = Mock(spec=Session)
    records = {(JudgeRunRecord, judge.judge_run_id): stored_judge,
               (JudgeValidationRunRecord, audit.id): stored_audit}
    session.get.side_effect = lambda model, identifier: records.get((model, identifier))
    debug = _debug_judge_runs(session, row)[0]
    assert debug.evidence_axes["S1"]["direction"] == "supports_claim"
    assert [n.source_quantity_id for n in debug.numeric_findings] == [
        "E1.U1.Q1", "E1.U1.Q2", "E1.U1.Q3"]
    assert "raw_model_content" not in debug.model_dump_json()
