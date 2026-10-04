"""Offline conditional fixtures, not clinical evidence or model calls."""

import asyncio
import hashlib
import json
from dataclasses import replace
from uuid import uuid4

import pytest

from app.evaluation.slice41_cases import CASES, ProbeCase, annotated_response, probe_judge
from app.judging.compact23 import prepare_compact23
from app.judging.source_units import materialize_content
from app.pipeline.numeric_effect import numeric_effect
from app.report.builder import build_report, semantic_report_hash
from app.report.explanation import build_explanation
from app.report.models import LensReport
from app.retrieval.evidence_pack import canonical_pack_bytes
from app.validation.joint23 import validate_joint23
from app.verdict.models import AggregationContext, AggregationInput, AggregationMode, ClaimFacts
from app.verdict.policy import POLICY_V4
from app.verdict.service import VerdictService
from tests.test_report import report_for
from tests.test_verdict import C, N, S


def fixture_report(case, *, second_finding=None):
    judge, pack = probe_judge(case)
    pico = pack.claim_snapshot.pico.model_copy(update={
        "numeric_effect": numeric_effect(case.claim),
    })
    snapshot = pack.claim_snapshot.model_copy(update={"pico": pico})
    digest = hashlib.sha256(canonical_pack_bytes(
        snapshot, pack.query_plan, pack.documents, pack.passages,
        pack.selected_evidence_ids, pack_version=pack.evidence_pack_version,
    )).hexdigest()
    pack = pack.model_copy(update={"claim_snapshot": snapshot, "snapshot_hash": digest})
    prepared = prepare_compact23(judge.evidence_pack_id, pack)
    response = annotated_response(case)
    if second_finding:
        raw = json.loads(judge.response_json["raw_model_content"])
        raw["statements"].append({**raw["statements"][0], "statement_id": "S2",
                                  "text": second_finding, "qualitative_finding": second_finding})
        raw["conclusion"]["based_on_statement_ids"].append("S2")
        raw_text = json.dumps(raw)
        decision = materialize_content(raw_text, prepared.input_snapshot_json)
        judge = judge.model_copy(update={
            "decision": decision,
            "response_json": {**decision.model_dump(mode="json"), "raw_model_content": raw_text},
        })
        response = response.model_copy(update={
            "attributions": (*response.attributions, response.attributions[0].model_copy(
                update={"statement_id": "S2"})),
            "assessments": (*response.assessments, response.assessments[0].model_copy(
                update={"statement_id": "S2", "direction": "opposes_claim"})),
        })
    judge = judge.model_copy(update={
        "evidence_pack_hash": digest, "input_snapshot_json": prepared.input_snapshot_json,
        "input_snapshot_hash": prepared.input_snapshot_hash,
        "prompt_hash": prepared.prompt_hash,
    })

    class OfflineValidator:
        provider = "fixture"
        model = "fixture"

        async def assess_joint23(self, prepared):
            return response

    judges = tuple(judge.model_copy(update={
        "judge_run_id": uuid4(), "slot": slot, "model_family": f"fixture-{slot}",
    }) for slot in (1, 2))
    validations = tuple(asyncio.run(validate_joint23(j, pack, OfflineValidator())) for j in judges)
    request = AggregationInput(
        claim_id=pack.claim_id, evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=digest, judge_run_ids=tuple(j.judge_run_id for j in judges),
        judge_validation_run_ids=tuple(v.id for v in validations),
        mode=AggregationMode.FIXTURE_OR_EVALUATION, policy_version=POLICY_V4.version,
    )
    context = AggregationContext(
        claim=ClaimFacts(claim_id=pack.claim_id, risk_class="standard",
                         normalization_status="normalized"), pack=pack,
        stored_pack_hash=digest, retrieval_status="ok", judges=judges, validations=validations,
    )
    verdict = VerdictService(POLICY_V4).aggregate(request, context)
    report = build_report(uuid4(), verdict, pack, judges, validations)
    return report, verdict, pack, judges, validations


@pytest.mark.parametrize("label,category", [
    (S, "supported_by_validated_evidence"), (C, "contradicted_by_validated_evidence"),
])
def test_qualitative_decisive(label, category):
    report, _, _ = report_for((label, label))
    assert report.verdict_explanation.reason_category == category
    assert report.verdict_explanation.established
    assert report.verdict_explanation.unresolved is None
    assert report.short_summary == report.verdict_explanation.summary


SMOKING = ProbeCase(
    "explanation-smoking85", "Smoking increases lung cancer risk by 85%.",
    "A systematic causal assessment finds that smoking increases lung cancer risk.",
    "Smoking increases lung cancer risk.", "supports_claim", role="synthesis",
    finding_basis="causal_assessment", design="systematic_review", exposure="Smoking",
    outcome="lung cancer risk", label="not_enough_evidence",
)


def test_numeric_nei_smoking_regression_and_generic_exposure():
    report, verdict, pack, judges, validations = fixture_report(SMOKING)
    explanation = report.verdict_explanation
    assert report.verdict == "not_enough_evidence"
    assert explanation.reason_category == "numeric_magnitude_unverified"
    assert explanation.summary == (
        "Validated evidence supports an increase in lung cancer risk with Smoking. "
        "The retrieved evidence does not establish the claimed 85% magnitude at a sufficiently "
        "comparable scope, so the specific magnitude could not be verified."
    )
    assert len(explanation.summary) <= 350
    assert explanation.evidence_ids == ("E1",)
    before = verdict.model_dump_json()
    assert build_explanation(verdict, pack, judges, validations, report.key_evidence) == explanation
    assert verdict.model_dump_json() == before
    generic = replace(SMOKING, id="generic-numeric", claim="X increases Y risk by 42%.",
                      exposure="X", outcome="Y risk",
                      source="A systematic causal assessment finds that X increases Y risk.",
                      finding="X increases Y risk.")
    other = fixture_report(generic)[0].verdict_explanation
    assert "42%" in other.summary and "Smoking" not in other.summary


@pytest.mark.parametrize("case_id,category", [
    ("association-causal", "causal_design_insufficient"),
    ("narrow-population", "population_mismatch"),
    ("narrow-dose", "scope_too_narrow"),
    ("carrot-reverse", "causal_design_insufficient"),
    ("conflicting-evidence", "conflicting_material_evidence"),
])
def test_specific_nei_axes(case_id, category):
    case = next(c for c in CASES if c.id == case_id)
    report = fixture_report(case)[0]
    assert report.verdict == "not_enough_evidence"
    assert report.verdict_explanation.reason_category == category
    if case_id == "carrot-reverse":
        assert "reverse causation" in report.short_summary


@pytest.mark.parametrize("basis,scope,role,category", [
    ("active_alternative", "incompatible", "direct", "comparator_mismatch"),
    ("endpoint", "incompatible", "direct", "outcome_mismatch"),
    ("other", "aligned", "contextual", "only_contextual_evidence"),
    ("other", "broader_or_indirect", "direct", "only_indirect_evidence"),
])
def test_other_nei_gaps(basis, scope, role, category):
    case = ProbeCase(f"explanation-{category}", "X increases Y.",
                     "The randomized X study measured a limited result.",
                     "The study measured a limited result.", "neutral", scope=scope,
                     scope_basis=basis, role=role, strength="insufficient",
                     label="not_enough_evidence")
    report = fixture_report(case)[0]
    assert report.verdict == "not_enough_evidence"
    assert report.verdict_explanation.reason_category == category


def test_numeric_estimates_not_comparable_do_not_imply_contradiction():
    case = replace(SMOKING, id="incomparable-numbers",
                   source="A randomized smoking study in a restricted population found "
                   "a lung cancer risk increase by 20%.",
                   finding="The restricted population had a lung cancer risk increase by 20%.",
                   scope="compatible_but_narrower", scope_basis="population", strength="supporting")
    report = fixture_report(case)[0]
    assert report.verdict == "not_enough_evidence"
    assert report.verdict_explanation.reason_category == "numeric_evidence_not_comparable"
    assert "not sufficiently comparable to establish contradiction" in report.short_summary
    assert report.verdict_explanation.established is None


def test_aligned_numeric_contradiction_preserves_established_direction():
    case = replace(SMOKING, id="aligned-numeric-contradiction", label="contradicted",
                   source="A randomized smoking study finds that smoking increases lung cancer "
                   "risk. Smoking increases lung cancer risk by 20%.",
                   design="randomized_controlled_trial", role="direct",
                   finding_basis="direct_result")
    report = fixture_report(case, second_finding="Smoking increases lung cancer risk by 20%.")[0]
    assert report.verdict == "contradicted"
    assert report.verdict_explanation.reason_category == "contradicted_by_validated_evidence"
    assert "increase in lung cancer risk" in report.verdict_explanation.established
    assert "conflicts with the claimed 85% magnitude" in report.verdict_explanation.unresolved


def test_numeric_direction_opposition_does_not_invent_agreement_on_direction():
    case = replace(SMOKING, id="numeric-wrong-direction", label="contradicted",
                   direction="opposes_claim", design="randomized_controlled_trial",
                   role="direct", finding_basis="direct_result",
                   source="A randomized smoking study found a decrease in lung cancer risk.",
                   finding="Smoking decreased lung cancer risk.")
    report = fixture_report(case)[0]
    assert report.verdict == "contradicted"
    assert "supports an increase" not in report.short_summary
    assert "magnitude" not in report.short_summary


def test_conflict_and_operational_failures_are_distinct():
    conflict = report_for((S, C, N))[0]
    assert conflict.verdict_explanation.reason_category == "conflicting_material_evidence"
    assert "both directions" in conflict.short_summary
    failed = report_for((S, None, None))[0]
    assert failed.verdict_explanation.reason_category == "technical_validation_failure"
    assert "2 assessments" in failed.short_summary
    assert failed.verdict_explanation.established is None
    assert not failed.verdict_explanation.evidence_ids
    insufficient = report_for((S,))[0]
    assert insufficient.verdict == "unable_to_verify_reliably"
    assert insufficient.verdict_explanation.reason_category == "insufficient_qualified_judges"


def test_rejected_attribution_and_unqualified_judge_never_establish_direction():
    rejected = replace(SMOKING, id="rejected-numeric", attribution="not_established_by_sources")
    report = fixture_report(rejected)[0]
    assert report.verdict == "unable_to_verify_reliably"
    assert report.verdict_explanation.established is None
    assert not report.verdict_explanation.evidence_ids


@pytest.mark.parametrize("version", ["1.0", "1.1", "1.2"])
def test_historical_report_shape_and_hash_are_unchanged(version):
    report = report_for((S, S))[0]
    payload = report.model_dump(mode="json")
    payload.pop("verdict_explanation")
    payload["report_version"] = payload["provenance"]["report_version"] = version
    if version != "1.2":
        for card in payload["key_evidence"]:
            for name in ("document_id", "source_kind", "organization", "document_purpose",
                         "analysis_design", "exposure_assignment", "attribution", "currency",
                         "excerpts"):
                card.pop(name, None)
    semantic = json.loads(json.dumps(payload))
    semantic.pop("semantic_hash")
    semantic["provenance"].pop("generated_at")
    expected = hashlib.sha256(json.dumps(semantic, sort_keys=True, ensure_ascii=False,
                                        separators=(",", ":")).encode()).hexdigest()
    historical = LensReport.model_validate(payload)
    assert historical.verdict_explanation is None
    assert "verdict_explanation" not in historical.model_dump(mode="json")
    assert semantic_report_hash(historical) == expected


def test_report_response_schema_exposes_typed_explanation():
    schema = LensReport.model_json_schema(mode="serialization")
    assert "verdict_explanation" in schema["properties"]
    assert schema["$defs"]["VerdictExplanation"]["properties"]["version"]["const"] == "1.0"
