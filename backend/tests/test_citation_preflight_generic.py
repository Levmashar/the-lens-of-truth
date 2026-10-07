"""Exact rejected-response replays and generic citation-contract adversarial tests.

These tests exercise reference integrity only. They do not assert medical truth or
request model/provider traffic.
"""

import asyncio
import gzip
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from app.judging.compact25 import prepare_compact25
from app.judging.models import ProviderResponse
from app.judging.service import DecisionFailure, JudgeService, parse_provider_decision
from app.judging.source_quantities import catalog_items, derive_catalog
from app.judging.source_units import normalize_parent_unit_ids
from tests.test_judging import decision_json, pack_for, slot

FROZEN = json.loads(gzip.decompress(
    Path(__file__).with_name("fixtures").joinpath(
        "citation_preflight_frozen_20261006.json.gz").read_bytes()))
SOURCE = (
    "A clinical synthesis evaluated E2 and E1 concentrations. "
    "The E999 assay was exploratory. Forty-one adults were studied; "
    "the measured increase was 20%."
)
FIELDS = ("text", "qualitative_finding", "justification", "qualitative_justification")


def content_fixture():
    prepared = prepare_compact25(uuid4(), pack_for(passage=SOURCE))
    snapshot = deepcopy(prepared.input_snapshot_json)
    unit = next(unit for unit in snapshot["source_units"] if unit["text"] == SOURCE)
    raw = {
        "statements": [{
            "statement_id": "S1", "text": "The source reports E2 concentrations.",
            "kind": "study_finding", "source_unit_ids": [unit["unit_id"]],
            "qualitative_finding": "The source reports E2 concentrations.",
            "source_quantity_ids": [], "numeric_dependency": False,
        }],
        "conclusion": {
            "based_on_statement_ids": ["S1"],
            "justification": "S1 reports the source's E2 concentrations.",
            "qualitative_justification": "S1 reports the source's E2 concentrations.",
            "numeric_dependency": False,
        },
        "uncertainty_reasons": [],
    }
    return raw, snapshot, prepared.selected_ids


def set_prose(raw, field, prose):
    owner = (raw["statements"][0] if field in {"text", "qualitative_finding"}
             else raw["conclusion"])
    owner[field] = prose


def parse(raw, snapshot, selected):
    return parse_provider_decision(json.dumps(raw), selected, snapshot=snapshot,
                                   allow_visible_siblings=True)[0]


def add_distinct_unit(snapshot, *, identifier="E77", text="E123 was measured in 50 adults."):
    first = snapshot["source_units"][0]
    unit = {**first, "unit_id": f"{identifier}.U1", "evidence_id": identifier,
            "text": text, "end": len(text),
            "passage_sha256": hashlib.sha256(text.encode()).hexdigest()}
    snapshot["source_units"].append(unit)
    snapshot["judge_visible_evidence_ids"].append(identifier)
    snapshot["source_quantity_catalog"] = derive_catalog(snapshot["source_units"])
    return unit


def failure_details(raw, snapshot, selected):
    with pytest.raises(DecisionFailure) as raised:
        parse(raw, snapshot, selected)
    errors = raised.value.citation_errors
    assert len(errors) == 1
    details = errors[0]
    assert details["exception_type"]
    assert details["message"]
    assert isinstance(details["expected_allowed_ids"], list)
    return raised.value, details


@pytest.mark.parametrize("reply", FROZEN["replies"],
                         ids=lambda row: f"judge-{row['slot']}-attempt-{row['attempt']}")
def test_all_six_original_rejected_replies_pass_exact_frozen_preflight(reply):
    snapshot = deepcopy(reply["snapshot"])
    before = deepcopy(snapshot)
    assert snapshot["validation_contract"] == "judge-validation-2.5"
    assert derive_catalog(snapshot["source_units"]) == snapshot["source_quantity_catalog"]
    normalized, _changes = normalize_parent_unit_ids(reply["content"], snapshot)
    decision, inferred = parse_provider_decision(
        normalized, tuple(FROZEN["selected_evidence_ids"]), snapshot=snapshot,
        allow_visible_siblings=True,
    )
    assert not inferred
    assert decision.schema_version == "2.5"
    assert decision.label is None
    assert decision.statements
    units = {unit["unit_id"]: unit for unit in snapshot["source_units"]}
    quantities = catalog_items(snapshot)
    for statement in decision.statements:
        assert set(statement.source_unit_ids) <= set(units)
        assert len(statement.source_quantity_ids) == len(set(statement.source_quantity_ids))
        for identifier in statement.source_quantity_ids:
            assert quantities[identifier].source_unit_id in statement.source_unit_ids
    assert snapshot == before


@pytest.mark.parametrize("field", FIELDS)
def test_bare_source_vocabulary_is_scientific_content_not_implicit_citation(field):
    raw, snapshot, selected = content_fixture()
    set_prose(raw, field, "The frozen source measures E2, E1 and E999 concentrations.")
    decision = parse(raw, snapshot, selected)
    assert len(decision.statements) == 1


@pytest.mark.parametrize("field", FIELDS)
def test_infinitive_study_does_not_turn_source_vocabulary_into_a_citation(field):
    raw, snapshot, selected = content_fixture()
    set_prose(raw, field, "To study E2 concentrations, the clinical data were pooled.")
    assert parse(raw, snapshot, selected).statements
    set_prose(raw, field, "According to study E999, the clinical data establish the finding.")
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_evidence_citation"
    assert details["offending_id"] == "E999"


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("explicit", ["[E999]", "E999.U1", "E999.U1.Q1", "source E999",
                                      "evidence E999", "study E999", "passage E999"])
def test_explicit_unknown_citation_is_strict_even_when_same_token_is_source_vocabulary(
    field, explicit,
):
    raw, snapshot, selected = content_fixture()
    set_prose(raw, field, f"The answer cites {explicit} to establish its finding.")
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_evidence_citation"
    assert details["statement_id"] == (
        "S1" if field in {"text", "qualitative_finding"} else None)
    assert details["offending_id"] == (explicit if ".U" in explicit else "E999")


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("prose", ["E999's results support this conclusion.",
                                  "E999 demonstrated a reliable effect.",
                                  "From E999, the claim is established."])
def test_source_vocabulary_does_not_exempt_explicit_publication_citation_context(field, prose):
    raw, snapshot, selected = content_fixture()
    set_prose(raw, field, prose)
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_evidence_citation"
    assert details["offending_id"] == "E999"


@pytest.mark.parametrize("field", FIELDS)
def test_unknown_bare_evidence_token_is_not_exempt_without_own_source_vocabulary(field):
    raw, snapshot, selected = content_fixture()
    set_prose(raw, field, "The answer claims E123 establishes its finding.")
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_evidence_citation"
    assert details["offending_id"] == "E123"


@pytest.mark.parametrize("field", FIELDS)
def test_unrelated_visible_source_cannot_exempt_an_unknown_prose_reference(field):
    raw, snapshot, selected = content_fixture()
    add_distinct_unit(snapshot)
    set_prose(raw, field, "The answer says E123 establishes its finding.")
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_evidence_citation"
    assert details["offending_id"] == "E123"


@pytest.mark.parametrize("field", ["justification", "qualitative_justification"])
def test_conclusion_vocabulary_uses_only_its_based_on_statements(field):
    raw, snapshot, selected = content_fixture()
    other = add_distinct_unit(snapshot)
    raw["statements"].append({
        **raw["statements"][0], "statement_id": "S2", "source_unit_ids": [other["unit_id"]],
        "text": "The second source reports E123 measurements.",
        "qualitative_finding": "The second source reports E123 measurements.",
    })
    set_prose(raw, field, "The conclusion mentions E123 measurements.")
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_evidence_citation"
    assert details["offending_id"] == "E123"
    raw["conclusion"]["based_on_statement_ids"] = ["S1", "S2"]
    assert parse(raw, snapshot, selected).conclusion.based_on_statement_ids == ("S1", "S2")


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("reference_kind", ["unit", "quantity"])
def test_other_statement_structured_references_are_not_borrowed(field, reference_kind):
    raw, snapshot, selected = content_fixture()
    other = add_distinct_unit(snapshot)
    quantity_id = next(identifier for identifier, quantity in catalog_items(snapshot).items()
                       if quantity.source_unit_id == other["unit_id"])
    raw["statements"].append({
        **raw["statements"][0], "statement_id": "S2", "source_unit_ids": [other["unit_id"]],
        "source_quantity_ids": [quantity_id], "text": "The second source measured 50 adults.",
        "qualitative_finding": "The second source examined a distinct sample.",
    })
    identifier = other["unit_id"] if reference_kind == "unit" else quantity_id
    set_prose(raw, field, f"This finding attributes its result to {identifier}.")
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_evidence_citation"
    assert details["offending_id"] == identifier


def test_unknown_unit_diagnostics_identify_statement_reference_and_frozen_allowed_set():
    raw, snapshot, selected = content_fixture()
    raw["statements"][0]["source_unit_ids"] = ["E999.U1"]
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_source_unit"
    assert details["statement_id"] == "S1"
    assert details["reference_field"] == "source_unit_ids"
    assert details["offending_id"] == "E999.U1"
    assert details["expected_allowed_ids"] == [
        unit["unit_id"] for unit in snapshot["source_units"]]


def test_duplicate_unit_reference_remains_invalid_with_specific_diagnostics():
    raw, snapshot, selected = content_fixture()
    identifier = raw["statements"][0]["source_unit_ids"][0]
    raw["statements"][0]["source_unit_ids"] = [identifier, identifier]
    _failure, details = failure_details(raw, snapshot, selected)
    assert details["statement_id"] == "S1"
    assert details["offending_id"] == identifier
    assert details["reference_field"] == "source_unit_ids"
    assert details["message"] == "Duplicate source unit"


def test_duplicate_publication_passages_keep_distinct_frozen_ids_and_unit_ownership():
    raw, snapshot, selected = content_fixture()
    add_distinct_unit(snapshot, text=SOURCE)
    units = snapshot["source_units"]
    own = next(unit for unit in units
               if unit["unit_id"] == raw["statements"][0]["source_unit_ids"][0])
    same_document = [unit for unit in units if unit["document_id"] == own["document_id"]
                     and unit["text"] == SOURCE]
    assert len(same_document) >= 2
    first, sibling = same_document[:2]
    assert first["evidence_id"] != sibling["evidence_id"]
    raw["statements"][0]["source_unit_ids"] = [first["unit_id"], sibling["unit_id"]]
    decision = parse(raw, snapshot, selected)
    assert {ref.evidence_id for ref in decision.statements[0].evidence_refs} == {
        first["evidence_id"], sibling["evidence_id"]}
    sibling_quantity = next(identifier for identifier, quantity in catalog_items(snapshot).items()
                            if quantity.source_unit_id == sibling["unit_id"])
    raw["statements"][0]["source_unit_ids"] = [first["unit_id"]]
    raw["statements"][0]["source_quantity_ids"] = [sibling_quantity]
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_source_quantity"
    assert details["source_unit_id"] == sibling["unit_id"]


def test_unique_frozen_parent_normalizes_but_unknown_or_ambiguous_parent_does_not():
    raw, snapshot, selected = content_fixture()
    unit = next(unit for unit in snapshot["source_units"] if unit["text"] == SOURCE)
    raw["statements"][0]["source_unit_ids"] = [unit["evidence_id"]]
    normalized, changes = normalize_parent_unit_ids(json.dumps(raw), snapshot)
    assert changes == [{"statement_id": "S1", "from": unit["evidence_id"],
                        "to": unit["unit_id"], "rule": "unique-frozen-parent-unit-1.0"}]
    assert parse(json.loads(normalized), snapshot, selected).statements[0].source_unit_ids == (
        unit["unit_id"],)
    raw["statements"][0]["source_unit_ids"] = ["E999"]
    assert normalize_parent_unit_ids(json.dumps(raw), snapshot)[1] == []
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_source_unit"
    assert details["offending_id"] == "E999"
    snapshot["source_units"].append({**unit, "unit_id": f"{unit['evidence_id']}.U2"})
    snapshot["source_quantity_catalog"] = derive_catalog(snapshot["source_units"])
    raw["statements"][0]["source_unit_ids"] = [unit["evidence_id"]]
    assert normalize_parent_unit_ids(json.dumps(raw), snapshot)[1] == []
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_source_unit"
    assert details["offending_id"] == unit["evidence_id"]


@pytest.mark.parametrize("field", FIELDS)
def test_explicit_local_reference_is_allowed_only_with_its_structured_owner(field):
    raw, snapshot, selected = content_fixture()
    unit = next(unit for unit in snapshot["source_units"] if unit["text"] == SOURCE)
    quantity_id = next(identifier for identifier, quantity in catalog_items(snapshot).items()
                       if quantity.source_unit_id == unit["unit_id"])
    raw["statements"][0]["source_quantity_ids"] = [quantity_id]
    set_prose(raw, field, f"Source [{unit['evidence_id']}] supplies {unit['unit_id']} "
                         f"with quantity {quantity_id}.")
    assert parse(raw, snapshot, selected).statements[0].source_quantity_ids == (quantity_id,)
    raw["statements"][0]["source_quantity_ids"] = []
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_evidence_citation"
    assert details["offending_id"] == quantity_id


@pytest.mark.parametrize("defect", ["unknown", "wrong_owner", "duplicate"])
def test_quantity_diagnostics_preserve_exact_ownership_and_uniqueness_checks(defect):
    raw, snapshot, selected = content_fixture()
    other = add_distinct_unit(snapshot)
    unit_ids = raw["statements"][0]["source_unit_ids"]
    quantities = catalog_items(snapshot)
    own = next(identifier for identifier, quantity in quantities.items()
               if quantity.source_unit_id in unit_ids)
    foreign = next(identifier for identifier, quantity in quantities.items()
                   if quantity.source_unit_id == other["unit_id"])
    selected_quantities = {"unknown": ["E999.U1.Q1"], "wrong_owner": [foreign],
                           "duplicate": [own, own]}[defect]
    raw["statements"][0]["source_quantity_ids"] = selected_quantities
    failure, details = failure_details(raw, snapshot, selected)
    assert failure.category == "invalid_source_quantity"
    assert details["statement_id"] == "S1"
    assert details["reference_field"] == "source_quantity_ids"
    assert details["offending_id"] == selected_quantities[-1]
    assert details["expected_allowed_ids"] == [
        identifier for identifier, quantity in quantities.items()
        if quantity.source_unit_id in unit_ids]
    assert details["expected_unit_ids"] == unit_ids
    if defect == "wrong_owner":
        assert details["source_unit_id"] == other["unit_id"]
        assert details["evidence_id"] == other["evidence_id"]


def test_frozen_quantity_catalog_cannot_be_repaired_by_the_source_vocabulary_rule():
    raw, snapshot, selected = content_fixture()
    snapshot["source_quantity_catalog"]["items"][0]["values"] = ["999"]
    with pytest.raises(DecisionFailure, match="schema_violation"):
        parse(raw, snapshot, selected)


def test_historical_v24_prose_guard_is_unchanged_even_with_source_vocabulary():
    raw, snapshot, selected = content_fixture()
    snapshot["validation_contract"] = "judge-validation-2.4"
    raw["label"] = "not_enough_evidence"
    raw["statements"][0]["text"] = "The source reports E999 concentrations."
    with pytest.raises(DecisionFailure, match="invalid_evidence_citation"):
        parse(raw, snapshot, selected)


def test_legacy_no_snapshot_prose_guard_is_unchanged():
    raw = json.loads(decision_json())
    raw["statements"][0]["text"] = "The source measured estradiol E2 concentrations."
    with pytest.raises(DecisionFailure, match="invalid_evidence_citation"):
        parse_provider_decision(json.dumps(raw), ("E1",))


def test_invalid_old_advisory_label_is_never_mapped_or_accepted():
    raw, snapshot, selected = content_fixture()
    snapshot["validation_contract"] = "judge-validation-2.4"
    raw["label"] = "conflicting_evidence"
    with pytest.raises(DecisionFailure, match="schema_violation"):
        parse(raw, snapshot, selected)
    legacy = json.loads(decision_json("conflicting_evidence"))
    with pytest.raises(DecisionFailure, match="unsupported_label"):
        parse_provider_decision(json.dumps(legacy), ("E1",))


def test_both_failed_attempts_persist_specific_reference_diagnostics_without_prose():
    raw, _snapshot, _selected = content_fixture()
    raw["statements"][0]["source_unit_ids"] = ["E999.U1"]
    raw["statements"][0]["text"] = "REFERENCE_DIAGNOSTIC_PROSE_SENTINEL"
    content = json.dumps(raw)

    class InvalidReferenceProvider:
        async def evaluate(self, _slot, _prepared):
            return ProviderResponse(content=content)

    pack = pack_for(passage=SOURCE)
    run = asyncio.run(JudgeService(
        {"fake": InvalidReferenceProvider()}, axes_development=True, axes_contract="2.5",
    ).run(uuid4(), pack, (slot(1),), app_env="development"))[0][0]
    assert run.outcome_status == "failed"
    assert run.error_category == "invalid_source_unit"
    assert run.attempt_count == 2
    rejected = run.response_json["rejected_responses"]
    failures = run.response_json["attempt_failures"]
    assert len(rejected) == len(failures) == 2
    for index, attempt in enumerate(rejected, 1):
        assert attempt["attempt"] == index
        assert attempt["content"] == content
        assert attempt["citation_errors"][0]["statement_id"] == "S1"
        assert attempt["citation_errors"][0]["offending_id"] == "E999.U1"
        assert attempt["citation_errors"][0]["expected_allowed_ids"]
        assert attempt["citation_errors"][0]["exception_type"] == "SourceUnitReferenceError"
        assert attempt["citation_errors"][0]["message"]
        assert "REFERENCE_DIAGNOSTIC_PROSE_SENTINEL" not in json.dumps(attempt["citation_errors"])
        assert failures[index - 1]["attempt"] == index
        assert failures[index - 1]["category"] == "invalid_source_unit"
