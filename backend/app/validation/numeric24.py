"""Numeric source fidelity from references only; compare after semantic scope."""

from app.judging.models import JudgeDecisionV2
from app.judging.source_quantities import catalog_items, check_quantity_refs
from app.judging.source_units import SourceUnit
from app.retrieval.models import EvidencePack
from app.validation.models import IssueCode, ValidationIssue
from app.validation.numeric_effects import (
    Measure,
    NumericClaimComparability,
    NumericFinding,
    NumericSourceFidelity,
    compare_to_claim,
)

VERSION = "numeric-reference-fidelity-2.4"
FINDING_VERSION = "numeric-reference-comparability-2.4"


def numeric_issues24(decision: JudgeDecisionV2, snapshot: dict[str, object]
                     ) -> tuple[ValidationIssue, ...]:
    if decision.schema_version not in {"2.4", "2.5"}:
        raise ValueError("Structured references require V2.4")
    try:
        catalog = catalog_items(snapshot)
    except ValueError:
        return (ValidationIssue(
            target_type="judge_statement", target_id="conclusion", evidence_refs=(),
            issue_code=IssueCode.PACK_HASH_MISMATCH, severity="fatal",
        ),)
    issues = []
    for statement in decision.statements:
        try:
            if statement.source_quantity_ids is None:
                raise ValueError("Missing quantity reference field")
            check_quantity_refs(statement.source_quantity_ids, statement.source_unit_ids, catalog)
        except ValueError:
            issues.append(ValidationIssue(
                target_type="judge_statement", target_id=statement.statement_id,
                evidence_refs=tuple(r.evidence_id for r in statement.evidence_refs),
                issue_code=IssueCode.SOURCE_QUANTITY_REFERENCE_INVALID, severity="fatal",
                numeric_diagnostic={"version": VERSION,
                                    "source_quantity_ids": statement.source_quantity_ids},
                conclusion_dependency=statement.statement_id in
                decision.conclusion.based_on_statement_ids,
            ))
    return tuple(issues)


def numeric_findings24(
    decision: JudgeDecisionV2, pack: EvidencePack, snapshot: dict[str, object], *,
    assessments: dict[str, tuple[str, str, bool]] | None = None,
) -> tuple[dict[str, object], ...]:
    """One diagnostic per statement/reference, independent of every generated prose field."""
    if numeric_issues24(decision, snapshot):
        return ()
    catalog = catalog_items(snapshot)
    raw_units = snapshot["source_units"]
    assert isinstance(raw_units, list)
    units = {u.unit_id: u for u in (SourceUnit.model_validate(raw) for raw in raw_units)}
    claim = pack.claim_snapshot.pico.numeric_effect if pack.claim_snapshot.pico else None
    result = []
    for statement in decision.statements:
        for identifier in statement.source_quantity_ids or ():
            quantity = catalog[identifier]
            typed = quantity.typed()
            fidelity = NumericSourceFidelity(
                status="verified", asserted=typed, source=typed,
                source_evidence_ids=(quantity.evidence_id,),
                reason="frozen_quantity_reference_and_owner_verified",
            )
            checked = assessments is not None and statement.statement_id in assessments
            if not checked or typed.kind == Measure.UNKNOWN:
                comparable = NumericClaimComparability(
                    status="uncertain", claim_measure=Measure(claim.kind) if claim else
                    Measure.UNKNOWN, reason="semantic_scope_pending" if not checked else
                    "unbound_source_quantity_cannot_establish_magnitude",
                )
                effect = "unresolved"
            else:
                assert assessments is not None
                scope, basis, allow_narrower = assessments[statement.statement_id]
                comparable, effect = compare_to_claim(
                    fidelity, claim, units[quantity.source_unit_id].text,
                    scope=scope, scope_basis=basis, allow_narrower=allow_narrower,
                    claim_scope_text=pack.claim_snapshot.standalone_text,
                )
            result.append(NumericFinding.model_validate({
                "version": FINDING_VERSION, "target_id": statement.statement_id,
                "source_quantity_id": identifier,
                "material": bool(statement.numeric_dependency or claim),
                "fidelity": fidelity, "comparability": comparable, "numeric_effect": effect,
                "semantic_scope_checked": checked, "structure_status": "structured",
            }).model_dump(mode="json"))
    return tuple(result)
