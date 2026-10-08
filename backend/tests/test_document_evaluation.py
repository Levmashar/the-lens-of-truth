"""Grouped engine safety and concurrency regressions; no paid or network calls."""

import asyncio
import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.adapters import document_models
from app.api.routes import analyses
from app.core.config import Settings
from app.core.errors import LensError
from app.document import evaluation, persistence, transport
from app.document.evaluation import (
    JUDGE_VERSION,
    VALIDATION_VERSION,
    GroupJudgeResponse,
    JudgeItem,
    aggregate_positions,
    evaluate_group,
    parse_group_items,
)
from app.document.models import DocumentAssertion, DocumentGroup, DocumentPlan, SourceSpan
from app.document.packaging import expand_quantity_view
from app.judging.models import JudgeSlot
from app.pipeline.pico import NormalizedPico
from app.retrieval.evidence_pack import build_evidence_pack
from app.retrieval.models import (
    AbstractSection,
    DocumentIntegrity,
    EvidencePack,
    PubMedDocument,
    RelationshipAnalysis,
)
from app.retrieval.passages import extract_passages
from app.retrieval.ranking import rank_passages
from tests.test_judging import pack_for

SOURCE = (
    "The prospective cohort found sunscreen use associated with melanoma incidence. "
    "The odds ratio was OR 3.92 compared with never use. "
    "The analysis adjusted for age and skin type. This is an observational association."
)
TRIAL = (
    "The unrelated randomized trial found daily sunscreen reduced melanoma incidence "
    "compared with discretionary use. The observed RR was 0.50."
)


def plan(texts: tuple[str, ...] | None = None) -> DocumentPlan:
    texts = texts or ("The cohort study reported sunscreen associated with melanoma.",)
    original = "\n".join(texts)
    assertions = []
    start = 0
    for index, text in enumerate(texts, 1):
        assertions.append(
            DocumentAssertion(
                assertion_id=f"A{index}",
                ordinal=index,
                kind="reported_study_fact",
                spans=(SourceSpan(start=start, end=start + len(text), text=text),),
                normalized_text=text,
                pico=NormalizedPico(
                    original_claim=text,
                    intervention_or_exposure="sunscreen",
                    outcome="melanoma",
                    claim_type="association",
                ),
            )
        )
        start += len(text) + 1
    return DocumentPlan(
        original_text=original,
        original_sha256=hashlib.sha256(original.encode()).hexdigest(),
        assertions=tuple(assertions),
        groups=(
            DocumentGroup(
                group_id="G1",
                title="Cohort findings",
                assertion_ids=tuple(a.assertion_id for a in assertions),
            ),
        ),
    )


def pack(*, contrary_trial: bool = False, integrity: str = "valid") -> EvidencePack:
    base = pack_for(
        claim=plan().original_text,
        passage=SOURCE,
        exposure="sunscreen",
        outcome="melanoma",
        claim_type="association",
    )
    cohort = base.documents[0].model_copy(
        update={
            "title": "Prospective cohort sunscreen report",
            "study_design": "cohort",
            "integrity": DocumentIntegrity(status=integrity),
            "relationship_analysis": RelationshipAnalysis(
                analysis_design="prospective_cohort", exposure_assignment="observed"
            ),
        }
    )
    documents = [cohort]
    if contrary_trial:
        documents.append(
            PubMedDocument(
                document_id="pubmed:456",
                pmid="456",
                title="Randomized sunscreen trial",
                abstract=TRIAL,
                abstract_sections=(AbstractSection(label="RESULTS", text=TRIAL),),
                canonical_url="https://pubmed.ncbi.nlm.nih.gov/456/",
                retrieved_at=datetime(2026, 10, 7, tzinfo=UTC),
                content_sha256="b" * 64,
                integrity=DocumentIntegrity(status="valid"),
                study_design="randomized_controlled_trial",
                relationship_analysis=RelationshipAnalysis(
                    analysis_design="randomized_intervention", exposure_assignment="randomized"
                ),
            )
        )
    ranked = rank_passages(
        base.claim_snapshot,
        tuple(documents),
        tuple(passage for document in documents for passage in extract_passages(document)),
    )
    return build_evidence_pack(base.claim_snapshot, base.query_plan, tuple(documents), ranked)


def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        debug_mode=False,
        judge_concurrency_limit=3,
        judge_1_provider="openai_compatible",
        judge_1_model="judge-one",
        judge_1_model_family="one",
        judge_1_base_url="https://example.invalid/v1",
        judge_1_api_key="fixture-only",
        judge_2_provider="openai_compatible",
        judge_2_model="judge-two",
        judge_2_model_family="two",
        judge_2_base_url="https://example.invalid/v1",
        judge_2_api_key="fixture-only",
        judge_3_provider="openai_compatible",
        judge_3_model="judge-three",
        judge_3_model_family="three",
        judge_3_base_url="https://example.invalid/v1",
        judge_3_api_key="fixture-only",
        validator_provider="openai_compatible",
        validator_model="validator",
        validator_base_url="https://example.invalid/v1",
        validator_api_key="fixture-only",
    )


def cohort_unit(sources):
    return next(
        unit
        for unit in sources["source_units"]
        if unit["document_id"] == "pubmed:123" and unit["text"] == SOURCE
    )


def judge_item(identifier, unit, *, quantities=()):
    return {
        "assertion_id": identifier,
        "status": "completed",
        "statements": [
            {
                "statement_id": "S1",
                "text": "The source reports an observational association.",
                "qualitative_finding": "The source reports an observational association.",
                "kind": "study_finding",
                "source_unit_ids": [unit["unit_id"]],
                "source_quantity_ids": list(quantities),
                "numeric_dependency": False,
            }
        ],
        "conclusion": "The frozen cohort reports this association.",
        "uncertainty_reasons": [],
    }


def semantic(evidence_id):
    return {
        "attributions": [
            {
                "statement_id": "S1",
                "evidence_ids": [evidence_id],
                "status": "supported_by_sources",
                "scope_match": "exact",
                "reason": "The finding describes the frozen source.",
                "numeric_independent": True,
            }
        ],
        "assessments": [
            {
                "statement_id": "S1",
                "direction": "neutral",
                "scope": "aligned",
                "strength": "insufficient",
                "role": "contextual",
                "scope_basis": "same_question",
                "finding_basis": "association",
                "reason": "Reporting an association does not establish causation.",
            }
        ],
        "missing_material_evidence": False,
    }


def validation_item(identifier, required, unit, sources):
    quantities = [
        q["quantity_id"]
        for q in expand_quantity_view(sources["source_quantity_catalog"])["items"]
        if q["source_unit_id"] == unit["unit_id"]
    ]
    return {
        "assertion_id": identifier,
        "status": "completed",
        "semantic": None if required else semantic(unit["evidence_id"]),
        "attributions": semantic(unit["evidence_id"])["attributions"] if required else [],
        "reporting_checks": [
            {
                "field": field,
                "status": "matches",
                "source_unit_ids": [unit["unit_id"]],
                "source_quantity_ids": quantities if field == "effect_value" else [],
                "reason": "The matched source explicitly reports this detail.",
            }
            for field in required
        ],
        "interpretation_limits": ["Observational association does not establish causation."],
        "reason": "",
    }


def responded(data):
    return {
        "status": "responded",
        "http_status": 200,
        "raw_response": json.dumps(data),
        "provider_latency_ms": 1,
        "queue_wait_ms": 0,
        "input_tokens": 20,
        "output_tokens": 20,
    }


def fake_transport(*, mutate_judge=None, mutate_validation=None, failed_slot=None, calls=None):
    async def complete(slot, **kwargs):
        payload = kwargs["payload"]
        if calls is not None:
            calls.append((slot.slot, kwargs["operation"], deepcopy(payload)))
        unit = cohort_unit(payload["sources"])
        if kwargs["operation"] == "document_judge":
            if slot.slot == failed_slot:
                return {
                    "status": "unavailable",
                    "http_status": 400,
                    "failure": "provider_http_error",
                }
            items = [judge_item(a["assertion_id"], unit) for a in payload["assertions"]]
            data = {"version": JUDGE_VERSION, "group_id": payload["group_id"], "items": items}
            if mutate_judge:
                mutate_judge(data, payload)
        else:
            items = [
                validation_item(
                    a["assertion_id"], a["required_reporting_fields"], unit, payload["sources"]
                )
                for a in payload["assertions"]
            ]
            data = {"version": VALIDATION_VERSION, "group_id": payload["group_id"], "items": items}
            if mutate_validation:
                mutate_validation(data, payload)
        return responded(data)

    return complete


def run(monkeypatch, *, document=None, evidence=None, **fake_options):
    document = document or plan()
    monkeypatch.setattr(evaluation, "complete_group", fake_transport(**fake_options))
    return asyncio.run(
        evaluate_group(
            document,
            document.groups[0],
            evidence or pack(),
            {"status": "identified", "matched_document_ids": ["pubmed:123"]},
            uuid4(),
            settings(),
        )
    )


@pytest.mark.parametrize("corruption", ["group", "version", "extra", "nonobject", "items_type"])
def test_corrupt_shared_envelope_cannot_salvage_any_item(corruption):
    data = {"version": JUDGE_VERSION, "group_id": "G1", "items": []}
    if corruption == "group":
        data["group_id"] = "another-group"
    elif corruption == "version":
        data["version"] = "wrong-version"
    elif corruption == "extra":
        data["untrusted_provenance"] = True
    elif corruption == "items_type":
        data["items"] = {}
    else:
        data = []
    with pytest.raises(ValueError):
        parse_group_items(
            json.dumps(data),
            version=JUDGE_VERSION,
            group_id="G1",
            expected=("A1",),
            item_type=JudgeItem,
        )


def test_missing_unknown_and_duplicate_assertion_ids_are_explicit_isolated_failures():
    unit = {"unit_id": "E1.U1"}
    data = {
        "version": JUDGE_VERSION,
        "group_id": "G1",
        "items": [
            judge_item("A1", unit),
            judge_item("A3", unit),
            judge_item("A3", unit),
            judge_item("A999", unit),
        ],
    }
    valid, failures = parse_group_items(
        json.dumps(data),
        version=JUDGE_VERSION,
        group_id="G1",
        expected=("A1", "A2", "A3"),
        item_type=JudgeItem,
    )
    assert tuple(valid) == ("A1",)
    assert failures["A2"] == "missing_assertion_response"
    assert failures["A3"] == "duplicate_assertion_response"
    assert failures["A999"] == "unknown_assertion_reference"


@pytest.mark.parametrize(
    "defect", ["foreign_unit", "foreign_quantity", "missing", "invalid_schema"]
)
def test_bad_item_isolated_without_replaying_good_sibling(monkeypatch, defect):
    document = plan(
        (
            "The study reported sunscreen associated with melanoma.",
            "The same study reported an observational association.",
        )
    )
    calls = []

    def mutate(data, payload):
        if defect == "missing":
            data["items"].pop()
        elif defect == "invalid_schema":
            data["items"][1]["unexpected"] = "invalid"
        else:
            key = "source_unit_ids" if defect == "foreign_unit" else "source_quantity_ids"
            data["items"][1]["statements"][0][key] = [
                "E999.U1" if defect == "foreign_unit" else "E999.U1.Q1"
            ]

    results = run(monkeypatch, document=document, mutate_judge=mutate, calls=calls)
    assert len(results) == 3
    assert all(r["items"]["A1"]["position"] == "supported" for r in results)
    assert all(r["items"]["A2"]["position"] is None for r in results)
    assert (
        len(calls) == 6
    )  # Three group judges and three partial validators, never one per assertion.
    assert all(
        len(payload["assertions"]) == 1
        for _, operation, payload in calls
        if operation == "document_validation"
    )


def test_foreign_quantity_ownership_rejected_even_if_the_quantity_exists(monkeypatch):
    def mutate(data, payload):
        foreign = next(
            q
            for q in expand_quantity_view(payload["sources"]["source_quantity_catalog"])["items"]
            if q["source_unit_id"] != cohort_unit(payload["sources"])["unit_id"]
        )
        data["items"][0]["statements"][0]["source_quantity_ids"] = [foreign["quantity_id"]]

    results = run(monkeypatch, evidence=pack(contrary_trial=True), mutate_judge=mutate)
    assert all(r["items"]["A1"]["position"] is None for r in results)
    assert all("uncited unit" in r["items"]["A1"]["failure"] for r in results)
    assert all("validation_call" not in r for r in results)


@pytest.mark.parametrize(
    "defect", ["invented_quote", "other_study", "missing_field", "foreign_axis"]
)
def test_reporting_validation_reference_and_quote_defects_fail_closed(monkeypatch, defect):
    def mutate(data, payload):
        item = data["items"][0]
        if defect == "invented_quote":
            item["reporting_checks"][0]["source_value"] = "This source never said this."
        elif defect == "other_study":
            unit = next(
                u for u in payload["sources"]["source_units"] if u["document_id"] == "pubmed:456"
            )
            item["reporting_checks"][0].update(source_unit_ids=[unit["unit_id"]])
        elif defect == "missing_field":
            item["reporting_checks"].pop()
        else:
            item["attributions"][0]["evidence_ids"] = ["E999"]

    results = run(monkeypatch, evidence=pack(contrary_trial=True), mutate_validation=mutate)
    assert all(r["items"]["A1"]["position"] is None for r in results)


@pytest.mark.parametrize("defect", ["missing_item", "foreign_quantity", "bad_quote"])
def test_invalid_validator_item_does_not_destroy_its_valid_sibling(monkeypatch, defect):
    document = plan(
        (
            "The study reported sunscreen associated with melanoma.",
            "The same study reported an observational association.",
        )
    )
    calls = []

    def mutate(data, payload):
        if defect == "missing_item":
            data["items"].pop()
        elif defect == "foreign_quantity":
            foreign = next(
                q
                for q in expand_quantity_view(payload["sources"]["source_quantity_catalog"])[
                    "items"
                ]
                if q["source_unit_id"] != cohort_unit(payload["sources"])["unit_id"]
            )
            data["items"][1]["reporting_checks"][0]["source_quantity_ids"] = [
                foreign["quantity_id"]
            ]
        else:
            data["items"][1]["reporting_checks"][0]["source_value"] = (
                "An invented source quotation."
            )

    results = run(
        monkeypatch,
        document=document,
        evidence=pack(contrary_trial=True),
        mutate_validation=mutate,
        calls=calls,
    )
    assert all(r["items"]["A1"]["position"] == "supported" for r in results)
    assert all(r["items"]["A2"]["position"] is None for r in results)
    assert len(calls) == 6


@pytest.mark.parametrize("phase", ["judge", "validator"])
def test_wrong_shared_group_fails_every_item_without_salvaging_inner_results(monkeypatch, phase):
    document = plan(
        (
            "The study reported sunscreen associated with melanoma.",
            "The same study reported an observational association.",
        )
    )
    calls = []

    def corrupt(data, payload):
        data["group_id"] = "foreign-shared-group"

    results = run(
        monkeypatch,
        document=document,
        calls=calls,
        **{"mutate_judge" if phase == "judge" else "mutate_validation": corrupt},
    )
    assert all(r["items"][aid]["position"] is None for r in results for aid in ("A1", "A2"))
    assert len(calls) == 6
    assert (
        all(operation == "document_judge" for _, operation, _ in calls)
        if phase == "judge"
        else (sum(operation == "document_validation" for _, operation, _ in calls) == 3)
    )


def test_contrary_trial_cannot_disprove_accurate_observational_reporting(monkeypatch):
    results = run(monkeypatch, evidence=pack(contrary_trial=True))
    assert all(r["items"]["A1"]["position"] == "supported" for r in results)
    assert all(
        any(
            "observed rather than randomly assigned" in limit
            for limit in r["items"]["A1"]["interpretation_limits"]
        )
        for r in results
    )


def test_reporting_target_uses_attribution_without_fabricating_clinical_axes(monkeypatch):
    calls = []
    results = run(monkeypatch, calls=calls)
    for result in results:
        item = result["items"]["A1"]
        assert item["position"] == "supported"
        assert item["semantic"] is None
        assert item["attributions"][0]["status"] == "supported_by_sources"
        assert "qualification" not in item
    for _, operation, payload in calls:
        if operation == "document_validation":
            assert payload["assertions"][0]["validation_target"] == "reporting_fidelity"
            assert "validated_statements" not in payload["assertions"][0]["semantic_input"]


@pytest.mark.parametrize("defect", ["failed_attribution", "wrong_statement", "ellipsis", "axes"])
def test_reporting_target_keeps_source_checks_strict(monkeypatch, defect):
    def mutate(data, payload):
        item = data["items"][0]
        if defect == "failed_attribution":
            item["attributions"][0]["status"] = "not_established_by_sources"
        elif defect == "wrong_statement":
            item["attributions"][0]["statement_id"] = "S2"
        elif defect == "ellipsis":
            item["reporting_checks"][0]["source_value"] = "The prospective cohort...melanoma."
        else:
            item["semantic"] = semantic(cohort_unit(payload["sources"])["evidence_id"])

    results = run(monkeypatch, mutate_validation=mutate)
    assert all(r["items"]["A1"]["position"] is None for r in results)


def test_legacy_reporting_semantic_null_remains_unavailable():
    document, evidence = plan(), pack()
    snapshot = evaluation.document_snapshot(uuid4(), evidence)
    unit = cohort_unit(snapshot)
    slot = JudgeSlot(
        slot=1,
        provider="offline",
        model="offline",
        model_family="offline",
        base_url="https://offline.invalid",
    )
    judge = evaluation.materialize_item(
        JudgeItem.model_validate_json(json.dumps(judge_item("A1", unit))), evidence, slot, snapshot
    )
    legacy = evaluation.ValidationItem(
        assertion_id="A1",
        status="completed",
        semantic=None,
        reporting_checks=(),
        interpretation_limits=(),
        reason="",
    )
    assert (
        evaluation.qualify_item(
            document.assertions[0], legacy, judge, evidence, snapshot, "identified", ("pubmed:123",)
        )["position"]
        is None
    )
    assert evaluation.validation_item_type("document-validation-1.0") is evaluation.ValidationItem


def test_failed_judge_keeps_successful_siblings_and_existing_quorum(monkeypatch):
    results = run(monkeypatch, failed_slot=2)
    assert [r["items"]["A1"]["position"] for r in results] == ["supported", None, "supported"]
    positions = [r["items"]["A1"]["position"] for r in results if r["items"]["A1"]["position"]]
    assert aggregate_positions(positions, app_env="test")[0] == "supported"
    assert aggregate_positions(positions[:1], app_env="test")[0] == "unable_to_verify_reliably"
    assert (
        aggregate_positions(positions, app_env="test", risk_class="high")[0]
        == "unable_to_verify_reliably"
    )
    assert (
        aggregate_positions(positions + ["supported"], app_env="production")[0]
        == "unable_to_verify_reliably"
    )


@pytest.mark.parametrize(
    "failure,status,expected_attempts",
    [
        ("RemoteProtocolError", None, 2),
        ("provider_http_error", 503, 2),
        ("provider_http_error", 400, 1),
        ("quota_exceeded", 403, 1),
    ],
)
def test_validator_retries_only_transient_transport_with_one_shared_deadline(
    monkeypatch, failure, status, expected_attempts
):
    fake = fake_transport()
    attempts = []

    async def transport(slot, **kwargs):
        if kwargs["operation"] == "document_validation":
            attempts.append((kwargs["attempt"], kwargs["deadline"]))
            if kwargs["attempt"] == 1:
                return {"status": "unavailable", "failure": failure, "http_status": status}
        return await fake(slot, **kwargs)

    monkeypatch.setattr(evaluation, "complete_group", transport)
    document = plan()
    results = asyncio.run(
        evaluate_group(
            document,
            document.groups[0],
            pack(),
            {"status": "identified", "matched_document_ids": ["pubmed:123"]},
            uuid4(),
            settings(),
        )
    )
    assert all(len(r["validation_attempts"]) == expected_attempts for r in results)
    assert all(
        r["items"]["A1"]["position"] == ("supported" if expected_attempts == 2 else None)
        for r in results
    )
    assert len(set(deadline for _, deadline in attempts)) == 3


def test_shared_passages_are_sent_once_and_judges_remain_blind_to_siblings(monkeypatch):
    calls = []
    run(monkeypatch, evidence=pack(contrary_trial=True), calls=calls)
    assert len(calls) == 6
    judge_inputs = [payload for _, operation, payload in calls if operation == "document_judge"]
    assert judge_inputs[0] == judge_inputs[1] == judge_inputs[2]
    for _, _, payload in calls:
        wire = json.dumps(payload)
        assert wire.count(SOURCE) == 1
        assert wire.count(TRIAL) == 1
        assert all(
            "abstract" not in d and "abstract_sections" not in d
            for d in payload["sources"]["documents"]
        )
        assert "other_judges" not in payload
        assert payload["original_context"] == plan().original_text


def test_corrupt_shared_pack_fails_before_any_provider_call(monkeypatch):
    calls = []
    with pytest.raises(ValueError, match="hash"):
        run(
            monkeypatch, evidence=pack().model_copy(update={"snapshot_hash": "0" * 64}), calls=calls
        )
    assert not calls


@pytest.mark.parametrize("integrity", ["unknown", "expression_of_concern"])
def test_reporting_keeps_existing_integrity_requirements(monkeypatch, integrity):
    results = run(monkeypatch, evidence=pack(integrity=integrity))
    assert all(r["items"]["A1"]["position"] is None for r in results)


def test_false_reported_adjustment_is_contradiction_of_reporting_not_a_medical_vote(monkeypatch):
    document = plan(("The analysis adjusted for age and outdoor time.",))

    def mutate(data, payload):
        check = next(
            c for c in data["items"][0]["reporting_checks"] if c["field"] == "adjustment_set"
        )
        check["status"] = "mismatch"

    results = run(monkeypatch, document=document, mutate_validation=mutate)
    assert all(r["items"]["A1"]["position"] == "contradicted" for r in results)
    assert all(
        "reported_adjustment_set_mismatch" in r["items"]["A1"]["reason_codes"] for r in results
    )


def test_bare_number_cannot_establish_measure_comparison_or_endpoint(monkeypatch):
    document = plan(("The study reported up to a 292% increased risk of melanoma.",))

    def mutate(data, payload):
        for check in data["items"][0]["reporting_checks"]:
            if check["field"] in {"effect_measure", "comparison", "endpoint"}:
                check["source_value"] = "3.92"

    results = run(monkeypatch, document=document, mutate_validation=mutate)
    assert all(r["items"]["A1"]["position"] != "supported" for r in results)


def test_odds_ratio_cannot_pass_as_a_percent_risk_increase_even_with_false_matches(monkeypatch):
    document = plan(("The study reported up to a 292% increased risk of melanoma.",))
    results = run(monkeypatch, document=document)
    assert all(r["items"]["A1"]["position"] != "supported" for r in results)


def test_independent_judges_overlap_and_validation_starts_when_each_is_ready(monkeypatch):
    timeline = []
    fake = fake_transport()

    async def tracking(slot, **kwargs):
        operation = kwargs["operation"]
        timeline.append((slot.slot, operation, "start", monotonic()))
        if operation == "document_judge":
            await asyncio.sleep(0.06 if slot.slot == 3 else 0.005)
        result = await fake(slot, **kwargs)
        timeline.append((slot.slot, operation, "end", monotonic()))
        return result

    monkeypatch.setattr(evaluation, "complete_group", tracking)
    document = plan()
    results = asyncio.run(
        evaluate_group(
            document,
            document.groups[0],
            pack(),
            {"status": "identified", "matched_document_ids": ["pubmed:123"]},
            uuid4(),
            settings(),
        )
    )
    assert all(r["items"]["A1"]["position"] == "supported" for r in results)
    judge_starts = [
        stamp
        for _, operation, state, stamp in timeline
        if operation == "document_judge" and state == "start"
    ]
    first_end = min(
        stamp
        for _, operation, state, stamp in timeline
        if operation == "document_judge" and state == "end"
    )
    assert max(judge_starts) < first_end
    fast_validator = next(
        stamp
        for _, operation, state, stamp in timeline
        if operation == "document_validation" and state == "start"
    )
    slow_end = next(
        stamp
        for number, operation, state, stamp in timeline
        if number == 3 and operation == "document_judge" and state == "end"
    )
    assert fast_validator < slow_end


def test_account_limiter_shares_credentials_but_not_other_accounts():
    async def check():
        first = JudgeSlot(
            slot=1,
            provider="openai_compatible",
            model="one",
            model_family="one",
            base_url="https://example.invalid/v1",
            api_key="account-one",
        )
        sibling = first.model_copy(update={"slot": 2, "model": "two"})
        other = first.model_copy(update={"api_key": "account-two"})
        assert transport.account_limiter(first, 3) is transport.account_limiter(sibling, 3)
        assert transport.account_limiter(first, 3) is not transport.account_limiter(other, 3)

    asyncio.run(check())


@pytest.mark.parametrize(
    "claimed,source",
    [
        (
            "The study reported sunscreen increases melanoma risk by 40%.",
            "The cohort reported sunscreen increases melanoma risk by 20%.",
        ),
        (
            "The study reported up to a 292% increased risk of melanoma.",
            "The cohort reported sunscreen increases melanoma risk by 292%.",
        ),
        (
            "The study reported sunscreen increases melanoma risk by 20%.",
            "The cohort reported up to a 20% increased risk of melanoma.",
        ),
        (
            "The study reported sunscreen increases melanoma risk by 20%.",
            "The cohort reported at most 20% higher risk of melanoma.",
        ),
        (
            "The study reported sunscreen reduces melanoma risk by 20%.",
            "The cohort reported sunscreen increases melanoma risk by 20%.",
        ),
    ],
)
def test_false_numeric_matches_cannot_change_a_value_or_erase_a_bound(
    monkeypatch,
    claimed,
    source,
):
    import sys

    monkeypatch.setattr(sys.modules[__name__], "SOURCE", source)
    results = run(monkeypatch, document=plan((claimed,)))
    assert all(r["items"]["A1"]["position"] != "supported" for r in results)


def test_matching_point_numeric_reporting_remains_supported(monkeypatch):
    import sys

    source = "The cohort reported sunscreen increases melanoma risk by 20%."
    monkeypatch.setattr(sys.modules[__name__], "SOURCE", source)
    results = run(monkeypatch, document=plan((source,)))
    assert all(r["items"]["A1"]["position"] == "supported" for r in results)


def test_numeric_match_requires_the_quantity_of_the_reported_result(monkeypatch):
    import sys

    exact = "The cohort reported sunscreen increases melanoma risk by 20%."
    monkeypatch.setattr(
        sys.modules[__name__], "SOURCE", exact + " Another endpoint increased by 40%."
    )

    def quote_only_target(data, payload):
        check = next(
            c for c in data["items"][0]["reporting_checks"] if c["field"] == "effect_value"
        )
        quantities = expand_quantity_view(payload["sources"]["source_quantity_catalog"])["items"]
        check["source_quantity_ids"] = [
            q["quantity_id"] for q in quantities if q["values"] == ["20"]
        ]

    results = run(
        monkeypatch,
        document=plan(("The study reported sunscreen increases melanoma risk by 40%.",)),
        mutate_validation=quote_only_target,
    )
    assert all(r["items"]["A1"]["position"] != "supported" for r in results)


def test_transport_retains_visible_response_and_usage_but_never_reasoning_or_credentials(
    monkeypatch,
):
    requests, events = [], []
    original_client = httpx.AsyncClient
    content = json.dumps({"version": JUDGE_VERSION, "group_id": "G1", "items": []})

    async def handle(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": content,
                            "reasoning_content": "Hidden provider reasoning must not be saved.",
                        },
                    }
                ],
                "usage": {"prompt_tokens": 23, "completion_tokens": 17},
            },
        )

    monkeypatch.setattr(
        document_models.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handle),
            **kwargs,
        ),
    )
    monkeypatch.setattr(
        document_models, "record_model_event", lambda **kwargs: events.append(kwargs)
    )
    slot = JudgeSlot(
        slot=1,
        provider="openai_compatible",
        model="test",
        model_family="one",
        base_url="https://example.invalid/v1/",
        api_key="fixture-credential-never-export",
    )
    result = asyncio.run(
        transport.complete_group(
            slot,
            role="judge_1",
            operation="document_judge",
            system="Untrusted data",
            payload={"group_id": "G1"},
            schema=GroupJudgeResponse,
            timeout=1,
        )
    )
    assert result["status"] == "responded"
    assert result["raw_response"] == content
    assert (result["input_tokens"], result["output_tokens"]) == (23, 17)
    assert "Hidden provider reasoning" not in json.dumps([result, events])
    assert slot.api_key not in json.dumps([result, events])
    assert str(requests[0].url) == "https://example.invalid/v1/chat/completions"
    body = json.loads(requests[0].content)
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["max_tokens"] == 8192
    assert "tools" not in body


def test_transport_rejects_a_cutoff_even_if_visible_json_is_valid(monkeypatch):
    original_client = httpx.AsyncClient
    content = json.dumps({"version": JUDGE_VERSION, "group_id": "G1", "items": []})
    monkeypatch.setattr(
        document_models.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "choices": [{"finish_reason": "length", "message": {"content": content}}],
                    },
                )
            ),
            **kwargs,
        ),
    )
    slot = JudgeSlot(
        slot=1,
        provider="openai_compatible",
        model="test",
        model_family="one",
        base_url="https://example.invalid/v1",
    )
    result = asyncio.run(
        transport.complete_group(
            slot,
            role="judge_1",
            operation="document_judge",
            system="Untrusted data",
            payload={},
            schema=GroupJudgeResponse,
            timeout=1,
        )
    )
    assert result["status"] == "unavailable"
    assert "raw_response" not in result


def test_account_queue_deadline_does_not_start_an_http_request(monkeypatch):
    def client(**kwargs):
        pytest.fail("HTTP must not start after queue deadline")

    monkeypatch.setattr(document_models.httpx, "AsyncClient", client)

    async def check():
        slot = JudgeSlot(
            slot=1,
            provider="openai_compatible",
            model="test",
            model_family="one",
            base_url="https://example.invalid/v1",
            api_key="queue-test",
        )
        limiter = transport.account_limiter(slot, 1)
        await limiter.acquire()
        try:
            result = await transport.complete_group(
                slot,
                role="judge_1",
                operation="document_judge",
                system="Untrusted data",
                payload={},
                schema=GroupJudgeResponse,
                timeout=1,
                concurrency=1,
                deadline=monotonic() + 0.01,
            )
            assert result["failure"] == "account_queue_deadline"
            assert result["provider_latency_ms"] == 0
        finally:
            limiter.release()

    asyncio.run(check())


def test_absolute_provider_deadline_bounds_mock_transport_and_releases_account(monkeypatch):
    original_client = httpx.AsyncClient

    async def handle(request):
        await asyncio.sleep(0.2)
        return httpx.Response(200, json={"choices": []})

    monkeypatch.setattr(
        document_models.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handle),
            **kwargs,
        ),
    )

    async def check():
        slot = JudgeSlot(
            slot=1,
            provider="openai_compatible",
            model="test",
            model_family="one",
            base_url="https://example.invalid/v1",
            api_key="absolute-test",
        )
        started = monotonic()
        result = await transport.complete_group(
            slot,
            role="judge_1",
            operation="document_judge",
            system="Untrusted data",
            payload={},
            schema=GroupJudgeResponse,
            timeout=0.01,
            concurrency=1,
        )
        assert result["status"] == "unavailable"
        assert monotonic() - started < 0.1
        limiter = transport.account_limiter(slot, 1)
        await asyncio.wait_for(limiter.acquire(), 0.01)
        limiter.release()

    asyncio.run(check())


def test_external_cancellation_is_not_swallowed_and_releases_account(monkeypatch):
    original_client = httpx.AsyncClient
    entered = asyncio.Event()

    async def handle(request):
        entered.set()
        await asyncio.sleep(30)
        return httpx.Response(200, json={"choices": []})

    monkeypatch.setattr(
        document_models.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handle),
            **kwargs,
        ),
    )

    async def check():
        slot = JudgeSlot(
            slot=1,
            provider="openai_compatible",
            model="test",
            model_family="one",
            base_url="https://example.invalid/v1",
            api_key="cancel-test",
        )
        task = asyncio.create_task(
            transport.complete_group(
                slot,
                role="judge_1",
                operation="document_judge",
                system="Untrusted data",
                payload={},
                schema=GroupJudgeResponse,
                timeout=10,
                concurrency=1,
            )
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        limiter = transport.account_limiter(slot, 1)
        await asyncio.wait_for(limiter.acquire(), 0.01)
        limiter.release()

    asyncio.run(check())


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_document_endpoint_keeps_production_gate_before_debug_projection(monkeypatch, app_env):
    calls = []
    monkeypatch.setattr(analyses, "get_run", lambda *args: calls.append("retention"))
    monkeypatch.setattr(
        persistence,
        "latest_document_artifact",
        lambda *args: SimpleNamespace(
            snapshot_json={"version": "document-report-1.0", "production_qualified": False},
        ),
    )
    monkeypatch.setattr(
        persistence,
        "load_document_artifacts",
        lambda *args: pytest.fail(
            "An unqualified production report must not load development traces",
        ),
    )
    with pytest.raises(LensError) as failure:
        asyncio.run(
            analyses.get_document_report(
                uuid4(),
                object(),
                Settings(
                    _env_file=None,
                    app_env=app_env,
                    debug_mode=True,
                ),
            )
        )
    assert failure.value.status_code == 403
    assert failure.value.code == "report_not_qualified"
    assert calls == ["retention"]


@pytest.mark.parametrize("debug", [False, True])
def test_document_endpoint_debug_projection_omits_prompts_and_does_no_evaluation(
    monkeypatch,
    debug,
):
    from tests.test_document_audit import artifact, fixture

    analysis_id, frozen, plan_row, evidence_rows, judge_rows = fixture(monkeypatch)
    report_row = artifact(analysis_id, "report", frozen)
    monkeypatch.setattr(analyses, "get_run", lambda *args: None)
    monkeypatch.setattr(
        persistence,
        "latest_document_artifact",
        lambda session, analysis_id, kind: report_row if kind == "report" else plan_row,
    )
    calls = []

    def load(*args):
        calls.append("parents")
        return [plan_row, *evidence_rows, *judge_rows, report_row]

    monkeypatch.setattr(persistence, "load_document_artifacts", load)
    monkeypatch.setattr(
        evaluation,
        "evaluate_group",
        lambda *args, **kwargs: pytest.fail(
            "Reading a document must never invoke the evaluation engine",
        ),
    )
    result = asyncio.run(
        analyses.get_document_report(
            analysis_id,
            object(),
            Settings(
                _env_file=None,
                app_env="test",
                debug_mode=debug,
            ),
        )
    )
    assert result["groups"] == frozen["groups"]
    assert "debug_group_runs" not in frozen
    assert calls == ["parents"]  # Even public reads independently audit the saved parents.
    if debug:
        assert len(result["debug_group_runs"]) == 3
        assert all(
            "group_input" not in row and "validation_input" not in row
            for row in result["debug_group_runs"]
        )
        assert (
            result["debug_group_runs"][0]["judge_attempts"]
            == judge_rows[0].snapshot_json["judge_attempts"]
        )
    else:
        assert "debug_group_runs" not in result


def test_document_endpoint_retention_guard_runs_before_artifact_loading(monkeypatch):
    def expired(*args):
        raise LensError(410, "analysis_expired", "Analysis has expired.")

    monkeypatch.setattr(analyses, "get_run", expired)
    monkeypatch.setattr(
        persistence,
        "latest_document_artifact",
        lambda *args: pytest.fail(
            "Expired analyses must not load retained document artifacts",
        ),
    )
    with pytest.raises(LensError) as failure:
        asyncio.run(analyses.get_document_report(uuid4(), object(), settings()))
    assert failure.value.status_code == 410


@pytest.mark.parametrize("corrupt", [False, True])
def test_document_endpoint_returns_safe_not_ready_or_invalid_audit(monkeypatch, corrupt):
    monkeypatch.setattr(analyses, "get_run", lambda *args: None)

    def artifact(*args):
        if corrupt:
            raise ValueError("Private snapshot mismatch details must stay internal")
        return None

    monkeypatch.setattr(persistence, "latest_document_artifact", artifact)
    with pytest.raises(LensError) as failure:
        asyncio.run(analyses.get_document_report(uuid4(), object(), settings()))
    assert failure.value.status_code == (503 if corrupt else 404)
    assert failure.value.code == ("document_audit_invalid" if corrupt else "document_not_ready")
    assert "Private snapshot" not in failure.value.message
