"""Backend-owned exact citation spans. No model-supplied offsets or hashes."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.judging.citation_errors import CitationReferenceError, SourceUnitReferenceError
from app.judging.models import (
    EvidenceRef,
    JudgeConclusion,
    JudgeDecisionV2,
    JudgeLabel,
    JudgeStatement,
    UncertaintyReason,
)


class SourceUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    unit_id: str
    evidence_id: str
    document_id: str
    document_sha256: str
    passage_sha256: str
    content_version: str
    start: int
    end: int
    text: str
    section: str


class UnitStatement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    statement_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    text: str = Field(min_length=5, max_length=600)
    kind: Literal["study_finding", "study_method", "limitation"]
    source_unit_ids: tuple[str, ...] = Field(min_length=1, max_length=4)


class JudgeContent(BaseModel):
    """Only semantic content belongs to the model; protocol metadata is caller-owned."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    label: JudgeLabel
    statements: tuple[UnitStatement, ...] = Field(min_length=1, max_length=8)
    conclusion: JudgeConclusion
    uncertainty_reasons: tuple[UncertaintyReason, ...]


class UnitStatement23(UnitStatement):
    qualitative_finding: str = Field(min_length=5, max_length=600)
    numeric_details: tuple[str, ...] = Field(max_length=4)
    numeric_dependency: bool


class Conclusion23(JudgeConclusion):
    qualitative_justification: str = Field(min_length=5, max_length=1200)
    numeric_dependency: bool


class JudgeContent23(JudgeContent):
    statements: tuple[UnitStatement23, ...] = Field(min_length=1, max_length=5)
    conclusion: Conclusion23


class UnitStatement24(UnitStatement):
    qualitative_finding: str = Field(min_length=5, max_length=600)
    source_quantity_ids: tuple[str, ...] = Field(max_length=32)
    numeric_dependency: bool


class JudgeContent24(JudgeContent):
    statements: tuple[UnitStatement24, ...] = Field(min_length=1, max_length=5)
    conclusion: Conclusion23


class JudgeContent25(BaseModel):
    """A label is optional, untrusted advisory text and never a vote."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    label: str | None = Field(default=None, max_length=200)
    statements: tuple[UnitStatement24, ...] = Field(min_length=1, max_length=5)
    conclusion: Conclusion23
    uncertainty_reasons: tuple[UncertaintyReason, ...]


def materialize_content(content: str, snapshot: dict[str, object]) -> JudgeDecisionV2:
    position = snapshot.get("validation_contract") == "judge-validation-2.5"
    structured = snapshot.get("validation_contract") in {"judge-validation-2.4",
                                                         "judge-validation-2.5"}
    axes = snapshot.get("validation_contract") == "judge-validation-2.3"
    proposed = (JudgeContent25 if position else JudgeContent24 if structured
                else JudgeContent23 if axes else JudgeContent).model_validate_json(content)
    catalog = None
    if structured:
        from app.judging.source_quantities import catalog_items

        catalog = catalog_items(snapshot)
    raw_units = snapshot.get("source_units")
    if not isinstance(raw_units, list):
        raise ValueError("Frozen source units missing")
    units = {unit.unit_id: unit for unit in
             (SourceUnit.model_validate(item) for item in raw_units)}
    statements: list[JudgeStatement] = []
    for statement in proposed.statements:
        if len(set(statement.source_unit_ids)) != len(statement.source_unit_ids):
            duplicate = next(identifier for index, identifier in
                             enumerate(statement.source_unit_ids)
                             if identifier in statement.source_unit_ids[:index])
            raise CitationReferenceError(
                "Duplicate source unit", statement_id=statement.statement_id,
                reference_field="source_unit_ids", offending_id=duplicate,
                expected_allowed_ids=tuple(units),
            )
        selected = []
        for identifier in statement.source_unit_ids:
            if identifier not in units:
                raise SourceUnitReferenceError(
                    identifier, statement_id=statement.statement_id,
                    reference_field="source_unit_ids", offending_id=identifier,
                    expected_allowed_ids=tuple(units),
                    source_unit_id=identifier,
                )
            selected.append(units[identifier])
        if isinstance(statement, UnitStatement24):
            from app.judging.source_quantities import QuantityReferenceError, check_quantity_refs

            assert catalog is not None
            try:
                check_quantity_refs(
                    statement.source_quantity_ids, statement.source_unit_ids, catalog,
                )
            except QuantityReferenceError as exc:
                exc.bind_statement(statement.statement_id)
                raise
        # One whole frozen passage is a unit: no decimal/CI/negation segmentation.
        refs = tuple(EvidenceRef(evidence_id=u.evidence_id, quote=u.text) for u in selected)
        evidence_ids = tuple(ref.evidence_id for ref in refs)
        if len(evidence_ids) != len(set(evidence_ids)):
            duplicate = next(identifier for index, identifier in enumerate(evidence_ids)
                             if identifier in evidence_ids[:index])
            raise CitationReferenceError(
                "duplicate statement evidence reference", statement_id=statement.statement_id,
                reference_field="evidence_refs.evidence_id", offending_id=duplicate,
                expected_allowed_ids=tuple(dict.fromkeys(u.evidence_id for u in units.values())),
                evidence_id=duplicate,
            )
        statements.append(JudgeStatement.model_validate({
            "statement_id": statement.statement_id, "text": statement.text,
            "kind": statement.kind, "source_unit_ids": statement.source_unit_ids,
            "evidence_refs": refs,
            **({"qualitative_finding": statement.qualitative_finding,
                "numeric_details": statement.numeric_details,
                "numeric_dependency": statement.numeric_dependency}
               if isinstance(statement, UnitStatement23) else {}),
            **({"qualitative_finding": statement.qualitative_finding,
                "source_quantity_ids": statement.source_quantity_ids,
                "numeric_dependency": statement.numeric_dependency}
               if isinstance(statement, UnitStatement24) else {}),
        }))
    return JudgeDecisionV2.model_validate_json(json.dumps({
        **proposed.model_dump(mode="json"),
        **({"label": None, "advisory_label": proposed.label} if position else {}),
        "schema_version": (
            "2.5" if position else "2.4" if structured else "2.3" if axes else
            "2.2" if snapshot.get("validation_contract") == "judge-validation-2.2" else "2.1"
        ),
        "statements": [s.model_dump(mode="json") for s in statements],
    }))


def normalize_parent_unit_ids(
    content: str, snapshot: dict[str, object],
) -> tuple[str, list[dict[str, str]]]:
    """Development transport repair for a unique frozen evidence parent ID.

    Only an exact evidence ID with exactly one frozen child unit may be expanded.
    Unknown IDs, ambiguous children, and all medical content remain untouched so
    the strict materializer can reject them. Callers must persist the conversions.
    """

    if len(content) > 65536:
        return content, []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content, []
    if not isinstance(data, dict) or not isinstance(data.get("statements"), list):
        return content, []
    raw_units = snapshot.get("source_units")
    if not isinstance(raw_units, list):
        return content, []
    by_evidence: dict[str, list[str]] = {}
    for item in raw_units:
        unit = SourceUnit.model_validate(item)
        by_evidence.setdefault(unit.evidence_id, []).append(unit.unit_id)
    changes: list[dict[str, str]] = []
    for statement in data["statements"]:
        if (not isinstance(statement, dict)
                or not isinstance(statement.get("source_unit_ids"), list)):
            continue
        statement_id = statement.get("statement_id")
        ids = statement["source_unit_ids"]
        for index, identifier in enumerate(ids):
            if (isinstance(identifier, str) and isinstance(statement_id, str)
                    and len(by_evidence.get(identifier, ())) == 1):
                child = by_evidence[identifier][0]
                if child != f"{identifier}.U1":
                    continue
                ids[index] = child
                changes.append({
                    "statement_id": statement_id, "from": identifier, "to": child,
                    "rule": "unique-frozen-parent-unit-1.0",
                })
    return (json.dumps(data, ensure_ascii=False) if changes else content), changes
