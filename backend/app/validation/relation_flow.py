"""One conditional relation batch, then a backend-only qualification audit."""

import asyncio
import json
import re
from uuid import UUID

import httpx

from app.judging.models import JudgeDecisionV2, JudgeRun, JudgeStatement
from app.pipeline.numeric_effect import numeric_effect
from app.retrieval.models import EvidencePack
from app.retrieval.sufficiency import design_fact, question_category
from app.validation.assertion_numeric import compare_assertion_numbers, quantities
from app.validation.models import (
    ConclusionJustification,
    ConclusionJustificationStatus,
    IssueCode,
    NumericAlignment,
    StatementAttribution,
    StatementAttributionStatus,
    ValidationIssue,
)
from app.validation.qualification import (
    VERSION as QUALIFIER_VERSION,
)
from app.validation.qualification import (
    ConclusionQualificationAudit,
    ConclusionQualifierInput,
    FindingQualificationInput,
    qualify_conclusion,
)
from app.validation.relations import (
    PROMPT_VERSION,
    RelationValidationAudit,
    canonical_hash,
    prepare_relation_input,
)
from app.validation.scope import compare_relation, compare_scope
from app.validation.semantic import SemanticValidator


def claim_magnitude_alignment(
    claim: str, statement: str, *, version: str = "legacy",
) -> NumericAlignment:
    """Conservative essential-effect check, not a new source attribution check.

    Only typed effect magnitudes trigger this guard. RR transformations use the
    existing assertion parser; HR/OR cannot silently substitute for risk reduction.
    Dates/sample sizes in a qualitative claim do not become effect assertions.
    An unmatched/ambiguous magnitude cannot qualify support, but does not by itself
    establish contradiction. Approximation tolerances are not invented.
    """
    if version == "numeric-effect-1.0":
        claimed = numeric_effect(claim)
        if claimed and claimed.kind == "fold_change":
            if claimed.status != "parsed" or claimed.value is None:
                return NumericAlignment.UNCERTAIN
            stated = numeric_effect(statement)
            if stated and stated.kind == "fold_change" and stated.value is not None:
                return (NumericAlignment.ALIGNED if stated.value == claimed.value
                        else NumericAlignment.MISMATCH)
            # A risk ratio can express a risk multiple; HR/OR cannot replace it.
            rr = tuple(q for q in quantities(statement) if q.kind == "relative_risk")
            if "risk" in claim.casefold() and len(rr) == 1:
                from decimal import Decimal

                return (NumericAlignment.ALIGNED if rr[0].values[0] == Decimal(claimed.value)
                        else NumericAlignment.MISMATCH)
            return NumericAlignment.UNCERTAIN
    normalized = re.sub(r"\b(?:about|approximately)\s+(?=\d)", "", claim, flags=re.I)
    if not any(q.kind in {"relative_risk", "odds_ratio", "hazard_ratio", "percent_change",
                          "percentage_points"} for q in quantities(normalized)):
        return NumericAlignment.NOT_APPLICABLE
    return compare_assertion_numbers(normalized, (statement,)).status


def build_relation_payload(
    pack: EvidencePack, statements: tuple[JudgeStatement, ...],
    *, magnitude_version: str = "legacy",
) -> tuple[dict[str, object], tuple[FindingQualificationInput, ...]]:
    """Backend-owned metadata, reused by the aggregator's audit recheck."""
    passages = {p.evidence_id: p for p in pack.passages}
    documents = {d.document_id: d for d in pack.documents}
    metadata: dict[str, list[dict[str, object]]] = {}
    for statement in statements:
        metadata[statement.statement_id] = []
        for ref in statement.evidence_refs:
            ranked = passages[ref.evidence_id]
            document = documents[ranked.passage.document_id]
            metadata[statement.statement_id].append({
                "evidence_id": ref.evidence_id, "study_design": document.study_design,
                "study_design_source": document.study_design_source,
                "integrity": document.integrity.status,
                "deterministic_scope": compare_scope(pack.claim_snapshot, document, ranked),
                "deterministic_relation": compare_relation(pack.claim_snapshot, document, ranked),
                "applicability_warnings": document.applicability_warnings,
                **({"evidence_design": design_fact(document).model_dump(mode="json")}
                   if pack.evidence_pack_version == "1.5" else {}),
            })
    payload: dict[str, object] = {
        "original_claim": pack.claim_snapshot.standalone_text,
        "claim_type": pack.claim_snapshot.claim_type,
        "pico": (pack.claim_snapshot.pico.model_dump(mode="json")
                 if pack.claim_snapshot.pico else None),
        "validated_statements": [{"statement_id": s.statement_id, "text": s.text,
                                  "kind": s.kind, "frozen_metadata": metadata[s.statement_id]}
                                 for s in statements],
    }
    findings = tuple(FindingQualificationInput(
        statement_id=s.statement_id,
        study_designs=tuple(str(m["study_design"]) for m in metadata[s.statement_id]),
        deterministic_scopes=tuple(str(m["deterministic_scope"])
                                   for m in metadata[s.statement_id]),
        deterministic_relations=tuple(str(m["deterministic_relation"])
                                      for m in metadata[s.statement_id]),
        claim_magnitude_alignment=claim_magnitude_alignment(
            pack.claim_snapshot.standalone_text, s.text, version=magnitude_version,
        ),
        integrity_statuses=tuple(str(m["integrity"]) for m in metadata[s.statement_id]),
        evidence_design_facts=tuple(design_fact(documents[passages[ref.evidence_id].passage.
                                                       document_id])
                                    for ref in s.evidence_refs)
        if pack.evidence_pack_version == "1.5" else (),
    ) for s in statements)
    return payload, findings


async def qualify_with_relations(
    judge: JudgeRun, pack: EvidencePack, attributions: tuple[StatementAttribution, ...],
    validator: SemanticValidator | None, validation_id: UUID,
    *, risk_class: str,
) -> tuple[ConclusionJustification, RelationValidationAudit, ConclusionQualificationAudit, int]:
    decision = judge.decision
    assert isinstance(decision, JudgeDecisionV2)
    available = {a.statement_id for a in attributions if
                 a.status == StatementAttributionStatus.SUPPORTED_BY_SOURCES
                 and not a.issues}
    # Check all passed findings, including counterevidence outside dependencies.
    statements = tuple(s for s in decision.statements if s.statement_id in available)
    payload, findings = build_relation_payload(pack, statements)
    prepared = prepare_relation_input(
        payload, judge_run_id=str(judge.judge_run_id), validation_run_id=str(validation_id),
        statement_ids=tuple(s.statement_id for s in statements),
        evidence_ids=tuple(dict.fromkeys(ref.evidence_id for s in statements
                                        for ref in s.evidence_refs)),
        prompt_version="claim-relation-1.3-2026-10-01"
        if pack.evidence_pack_version == "1.5" else PROMPT_VERSION,
    )
    exact_input = json.loads(prepared.user_prompt.split("\n", 1)[1])
    audit = RelationValidationAudit(
        prompt_version="claim-relation-1.3-2026-10-01"
        if pack.evidence_pack_version == "1.5" else PROMPT_VERSION,
        provider=validator.provider if validator else None,
        model=validator.model if validator else None, prompt_hash=prepared.prompt_hash,
        input_hash=canonical_hash(exact_input), input_json=exact_input,
    )
    calls = 0
    if validator is None or not statements:
        audit = audit.model_copy(update={"error_category": "relation_validator_unavailable"})
    else:
        calls = 1
        try:
            async with asyncio.timeout(18.0):
                response = await validator.assess_relations(prepared)
            if tuple(a.statement_id for a in response.assessments) != prepared.statement_ids:
                raise ValueError("Relation batch ID mismatch")
            audit = audit.model_copy(update={"assessments": response.assessments})
        except (TimeoutError, httpx.TimeoutException):
            audit = audit.model_copy(update={"error_category": "relation_validator_timeout"})
        except (ValueError, TypeError, KeyError):
            audit = audit.model_copy(update={"error_category": "relation_validator_schema_failure"})
        except Exception:
            audit = audit.model_copy(update={
                "error_category": "relation_validator_transport_failure",
            })
    defects = tuple(issue for a in attributions for issue in a.issues)
    inputs = ConclusionQualifierInput(
        proposed_label=decision.label, claim_type=pack.claim_snapshot.claim_type,
        risk_class=risk_class,
        findings=findings, relations=audit.assessments,
        based_on_statement_ids=decision.conclusion.based_on_statement_ids, defects=defects,
        required_findings_available=(not audit.error_category and
                                     set(decision.conclusion.based_on_statement_ids) <= available),
        evidence_policy=("question-evidence-1.0" if pack.evidence_pack_version == "1.5"
                         else "legacy-1.0"),
        question_category=question_category(pack.claim_snapshot)
        if pack.evidence_pack_version == "1.5" else "other",
    )
    qualification = ConclusionQualificationAudit(
        version="conclusion-qualifier-1.1" if pack.evidence_pack_version == "1.5"
        else QUALIFIER_VERSION, input=inputs, output=qualify_conclusion(inputs),
    )
    dependencies = set(decision.conclusion.based_on_statement_ids)
    evidence_ids = tuple(dict.fromkeys(ref.evidence_id for s in decision.statements
                                      if s.statement_id in dependencies for ref in s.evidence_refs))
    status = (ConclusionJustificationStatus.UNABLE_TO_ASSESS if audit.error_category
              else qualification.output.status)
    issues: tuple[ValidationIssue, ...] = ()
    if status == ConclusionJustificationStatus.NOT_JUSTIFIED:
        issues = (ValidationIssue(
            target_type="judge_statement", target_id="conclusion", evidence_refs=evidence_ids,
            issue_code=IssueCode.CONCLUSION_NOT_JUSTIFIED, severity="fatal",
        ),)
    conclusion = ConclusionJustification(
        status=status, based_on_statement_ids=decision.conclusion.based_on_statement_ids,
        evidence_ids=evidence_ids, reason="; ".join(qualification.output.reason_codes),
        issues=issues,
        validator_provenance={"deterministic_qualifier_version": qualification.version,
                              "relation_prompt_version": audit.prompt_version,
                              "relation_prompt_hash": audit.prompt_hash},
    )
    return conclusion, audit, qualification, calls
