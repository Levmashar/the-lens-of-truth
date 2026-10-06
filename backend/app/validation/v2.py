"""Statement attribution, then conclusion justification, on frozen judge input."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from app.judging.models import JudgeDecisionV2, JudgeRun
from app.judging.prompt import (
    input_snapshot_hash,
    prepare_judge_input,
)
from app.judging.source_units import materialize_content
from app.retrieval.models import EvidencePack
from app.validation.assertion_numeric import compare_assertion_numbers
from app.validation.models import (
    ConclusionJustification,
    ConclusionJustificationStatus,
    IssueCode,
    JudgeValidationResult,
    JudgeValidationRun,
    NumericAlignment,
    SemanticScope,
    StatementAttribution,
    StatementAttributionStatus,
    ValidationIssue,
    ValidationStatus,
)
from app.validation.numeric import compare_statement_numbers
from app.validation.qualification import ConclusionQualificationAudit, qualify_conclusion
from app.validation.relation_flow import qualify_with_relations
from app.validation.relations import RelationValidationAudit
from app.validation.semantic import PROMPT_VERSION, SemanticValidator, prepare_semantic_input

VALIDATION_VERSION = "judge-validation-2.0"
DETERMINISTIC_VERSION = "statement-quote-numeric-2.0"


def _issue(
    code: IssueCode, statement_id: str, refs: tuple[str, ...], *,
    observed: str | None = None, source: str | None = None,
    measure: str | None = None, severity: str = "fatal",
) -> ValidationIssue:
    return ValidationIssue(
        target_type="judge_statement", target_id=statement_id,
        evidence_refs=refs, issue_code=code, observed_value=observed,
        source_value=source, measure_type=measure,
        severity="fatal" if severity == "fatal" else "warning",
    )


async def validate_v2(
    judge: JudgeRun, pack: EvidencePack, validator: SemanticValidator | None,
    *, timeout_seconds: float = 45.0, risk_class: str = "standard",
) -> JudgeValidationRun:
    decision = judge.decision
    if not isinstance(decision, JudgeDecisionV2):
        raise ValueError("V2 validation requires a V2 decision")
    started_at, start = datetime.now(UTC), monotonic()
    validation_id = uuid4()
    unit_contract = decision.schema_version in {"2.1", "2.2", "2.3", "2.4", "2.5"}
    relation_contract = decision.schema_version == "2.2"
    validation_version = f"judge-validation-{decision.schema_version}"
    prepared = prepare_judge_input(
        judge.evidence_pack_id, pack,
        version=f"judge-input-{decision.schema_version}",
    )
    snapshot_valid = (
        judge.input_snapshot_version == prepared.input_snapshot_version
        and judge.input_snapshot_hash == prepared.input_snapshot_hash
        and judge.input_snapshot_json is not None
        and input_snapshot_hash(judge.input_snapshot_json) == prepared.input_snapshot_hash
        and judge.evidence_pack_hash == pack.snapshot_hash
        and judge.claim_id == pack.claim_id
    )
    if unit_contract and snapshot_valid:
        try:
            rematerialized = materialize_content(json.dumps({
                "label": decision.advisory_label if decision.schema_version == "2.5"
                else decision.label,
                "statements": [{k: v for k, v in s.model_dump(mode="json").items()
                                if k != "evidence_refs"}
                               for s in decision.statements],
                "conclusion": decision.conclusion.model_dump(mode="json"),
                "uncertainty_reasons": decision.uncertainty_reasons,
            }), prepared.input_snapshot_json)
            snapshot_valid = rematerialized == decision
        except (ValueError, KeyError):
            snapshot_valid = False
    passage_map = {item.evidence_id: item for item in pack.passages}
    document_map = {item.document_id: item for item in pack.documents}
    visible = set(prepared.selected_ids) if snapshot_valid else set()
    from app.judging.compact23 import VERSION as AXES_COMPACT_VERSION
    from app.judging.compact24 import VERSION as STRUCTURED_COMPACT_VERSION
    from app.judging.compact25 import VERSION as POSITION_COMPACT_VERSION

    if (snapshot_valid and (decision.schema_version, judge.prompt_version) in {
        ("2.3", AXES_COMPACT_VERSION), ("2.4", STRUCTURED_COMPACT_VERSION),
        ("2.5", POSITION_COMPACT_VERSION),
    }):
        # The current development prompt exposes complete sections of selected
        # documents. Their exact frozen child units are citable; other Pack
        # passages remain excluded. Historical prompt contracts stay unchanged.
        raw_visible = prepared.input_snapshot_json.get("judge_visible_evidence_ids")
        if isinstance(raw_visible, list) and all(isinstance(i, str) for i in raw_visible):
            visible = set(raw_visible)
    calls = 0
    prompt_hashes: list[str] = []
    error_category: str | None = None
    relation_audit: RelationValidationAudit | None = None
    qualification_audit: ConclusionQualificationAudit | None = None

    async def one_statement(statement: object) -> StatementAttribution:
        nonlocal calls, error_category
        assert isinstance(statement, type(decision.statements[0]))
        ids = tuple(ref.evidence_id for ref in statement.evidence_refs)
        issues: list[ValidationIssue] = []
        frozen: list[dict[str, object]] = []
        quotes: list[str] = []
        numeric_diagnostic: dict[str, object] | None = None
        if not snapshot_valid:
            issues.append(_issue(IssueCode.PACK_HASH_MISMATCH, statement.statement_id, ids))
        for ref in statement.evidence_refs:
            item = passage_map.get(ref.evidence_id)
            document = document_map.get(item.passage.document_id) if item else None
            if item is None or ref.evidence_id not in visible:
                issues.append(_issue(IssueCode.CITATION_NOT_SELECTED,
                                     statement.statement_id, (ref.evidence_id,)))
                continue
            if document is None or not document.canonical_url or not (
                document.pmid or document.authoritative
            ):
                issues.append(_issue(IssueCode.DOCUMENT_PROVENANCE_MISSING,
                                     statement.statement_id, (ref.evidence_id,)))
                continue
            if document.integrity.status == "retracted":
                issues.append(_issue(IssueCode.RETRACTED_CITATION,
                                     statement.statement_id, (ref.evidence_id,)))
            if ref.quote not in item.passage.text:
                issues.append(_issue(IssueCode.QUOTE_NOT_IN_FROZEN_PASSAGE,
                                     statement.statement_id, (ref.evidence_id,),
                                     observed=ref.quote))
            quotes.append(ref.quote)
            frozen.append({
                "evidence_id": ref.evidence_id, "section": item.passage.section,
                "passage": item.passage.text,
                "title": document.title, "pmid": document.pmid,
                "study_design": document.study_design,
                "integrity": document.integrity.status,
                **({"analysis_design": document.relationship_analysis.model_dump(mode="json")
                    if document.relationship_analysis else None,
                    "source_kind": document.source_kind,
                    "authoritative": document.authoritative.model_dump(mode="json")
                    if document.authoritative else None}
                   if pack.evidence_pack_version == "1.5" else {}),
            })
        if not issues and unit_contract and decision.schema_version not in {"2.3", "2.4", "2.5"}:
            check = compare_assertion_numbers(
                statement.text, tuple(quotes),
                                              user_claim=pack.claim_snapshot.standalone_text)
            numeric_diagnostic = check.diagnostic()
            numeric_diagnostic["source_unit_ids"] = list(statement.source_unit_ids)
            if check.status in {NumericAlignment.MISMATCH, NumericAlignment.UNCERTAIN}:
                issues.append(_issue(
                    IssueCode.STATEMENT_NUMERIC_MISMATCH if check.status ==
                    NumericAlignment.MISMATCH else IssueCode.NUMERIC_UNCERTAIN,
                    statement.statement_id, ids,
                    observed=str(check.asserted.values) if check.asserted else statement.text,
                    source=str([q.values for q in check.candidates]),
                    measure=check.asserted.kind if check.asserted else "unclassified",
                    severity="fatal" if check.status == NumericAlignment.MISMATCH else "warning",
                ).model_copy(update={"numeric_diagnostic": numeric_diagnostic,
                                     "conclusion_dependency": statement.statement_id in
                                     decision.conclusion.based_on_statement_ids}))
        elif not issues and not unit_contract:
            numeric, asserted, observed = compare_statement_numbers(
                statement.text, " ".join(quotes),
            )
            if numeric == NumericAlignment.MISMATCH:
                assert asserted is not None and observed is not None
                issues.append(_issue(
                    IssueCode.STATEMENT_NUMERIC_MISMATCH, statement.statement_id, ids,
                    observed=str(asserted.values), source=str(observed.values),
                    measure=asserted.kind,
                ))
            elif numeric == NumericAlignment.UNCERTAIN:
                issues.append(_issue(IssueCode.NUMERIC_UNCERTAIN,
                                     statement.statement_id, ids, severity="warning"))
        fatal = any(issue.severity == "fatal" for issue in issues)
        if fatal:
            return StatementAttribution(
                statement_id=statement.statement_id, evidence_ids=ids,
                status=StatementAttributionStatus.NOT_ESTABLISHED_BY_SOURCES,
                reason="Frozen reference, quotation, or numeric attribution failed.",
                issues=tuple(issues),
            )
        if validator is None:
            return StatementAttribution(
                statement_id=statement.statement_id, evidence_ids=ids,
                status=StatementAttributionStatus.UNABLE_TO_ASSESS,
                reason="No semantic attribution validator is configured.",
                issues=tuple(issues),
            )
        semantic = prepare_semantic_input(
            "statement_attribution", {
                "statement": statement.model_dump(mode="json"),
                "frozen_passages": frozen,
                "numeric_verification": numeric_diagnostic,
            }, judge_run_id=str(judge.judge_run_id),
            validation_run_id=str(validation_id),
            statement_ids=(statement.statement_id,), evidence_ids=ids,
        )
        prompt_hashes.append(semantic.prompt_hash)
        calls += 1
        try:
            async with asyncio.timeout(18.0):
                response = await validator.assess_statement(semantic)
            if response.statement_id != statement.statement_id or response.evidence_ids != ids:
                raise ValueError("semantic statement references differ from request")
        except (TimeoutError, ValueError, TypeError):
            error_category = "statement_validator_unavailable"
            return StatementAttribution(
                statement_id=statement.statement_id, evidence_ids=ids,
                status=StatementAttributionStatus.UNABLE_TO_ASSESS,
                reason="Statement semantic validation was unavailable.",
                issues=tuple(issues),
            )
        except Exception:
            error_category = "statement_validator_unavailable"
            return StatementAttribution(
                statement_id=statement.statement_id, evidence_ids=ids,
                status=StatementAttributionStatus.UNABLE_TO_ASSESS,
                reason="Statement semantic validation was unavailable.",
                issues=tuple(issues),
            )
        if response.status in {
            StatementAttributionStatus.CONTRADICTED_BY_SOURCES,
            StatementAttributionStatus.NOT_ESTABLISHED_BY_SOURCES,
        }:
            issues.append(_issue(IssueCode.STATEMENT_ATTRIBUTION_FAILED,
                                 statement.statement_id, ids))
        return StatementAttribution(
            statement_id=statement.statement_id, evidence_ids=ids,
            status=response.status, scope_match=response.scope_match,
            reason=response.reason, issues=tuple(issues),
            validator_provenance={
                "provider": validator.provider, "model": validator.model,
                "prompt_version": PROMPT_VERSION, "prompt_hash": semantic.prompt_hash,
            },
        )

    try:
        async with asyncio.timeout(timeout_seconds):
            attributions = tuple(await asyncio.gather(
                *(one_statement(statement) for statement in decision.statements)
            ))
            by_id = {item.statement_id: item for item in attributions}
            dependencies = tuple(by_id[key] for key in decision.conclusion.based_on_statement_ids)
            conclusion_ids = tuple(dict.fromkeys(
                ref for item in dependencies for ref in item.evidence_ids
            ))
            unavailable_dependency = any(
                item.status == StatementAttributionStatus.UNABLE_TO_ASSESS
                for item in dependencies
            )
            uncertain_quantity = unit_contract and any(
                issue.issue_code == IssueCode.NUMERIC_UNCERTAIN
                for item in dependencies for issue in item.issues
            )
            bad_dependency = any(
                item.status != StatementAttributionStatus.SUPPORTED_BY_SOURCES
                or any(issue.severity == "fatal" or (unit_contract and
                       issue.issue_code == IssueCode.NUMERIC_UNCERTAIN) for issue in item.issues)
                for item in dependencies
            )
            if relation_contract:
                conclusion, relation_audit, qualification_audit, relation_calls = (
                    await qualify_with_relations(
                        judge, pack, attributions, validator, validation_id, risk_class=risk_class,
                    )
                )
                calls += relation_calls
                if relation_calls:
                    prompt_hashes.append(relation_audit.prompt_hash)
                error_category = error_category or relation_audit.error_category
            elif unavailable_dependency:
                conclusion = ConclusionJustification(
                    status=ConclusionJustificationStatus.UNABLE_TO_ASSESS,
                    based_on_statement_ids=decision.conclusion.based_on_statement_ids,
                    evidence_ids=conclusion_ids,
                    reason="A required statement assessment was unavailable.",
                )
            elif uncertain_quantity:
                conclusion = ConclusionJustification(
                    status=ConclusionJustificationStatus.UNCERTAIN,
                    based_on_statement_ids=decision.conclusion.based_on_statement_ids,
                    evidence_ids=conclusion_ids,
                    reason="A required quantitative assignment remains unresolved.",
                )
            elif bad_dependency:
                conclusion = ConclusionJustification(
                    status=ConclusionJustificationStatus.NOT_JUSTIFIED,
                    based_on_statement_ids=decision.conclusion.based_on_statement_ids,
                    evidence_ids=conclusion_ids,
                    reason="A required statement was not attributed to its sources.",
                    issues=(_issue(IssueCode.INVALID_CONCLUSION_PREMISE, "conclusion",
                                   conclusion_ids),),
                )
            elif (decision.label is not None and decision.label.value != "not_enough_evidence"
                  and any(item.scope_match == SemanticScope.MISMATCH
                          for item in dependencies)):
                conclusion = ConclusionJustification(
                    status=ConclusionJustificationStatus.NOT_JUSTIFIED,
                    based_on_statement_ids=decision.conclusion.based_on_statement_ids,
                    evidence_ids=conclusion_ids,
                    reason="A relied-on finding has a known incompatible scope.",
                    issues=(_issue(IssueCode.MATERIAL_SCOPE_MISMATCH, "conclusion",
                                   conclusion_ids),),
                )
            elif validator is None:
                conclusion = ConclusionJustification(
                    status=ConclusionJustificationStatus.UNABLE_TO_ASSESS,
                    based_on_statement_ids=decision.conclusion.based_on_statement_ids,
                    evidence_ids=conclusion_ids,
                    reason="No conclusion validator is configured.",
                )
            else:
                semantic = prepare_semantic_input(
                    "conclusion_justification", {
                        "original_claim": pack.claim_snapshot.standalone_text,
                        "claim_type": pack.claim_snapshot.claim_type,
                        "pico": (pack.claim_snapshot.pico.model_dump(mode="json")
                                 if pack.claim_snapshot.pico else None),
                        "proposed_label": decision.label,
                        "judge_conclusion": decision.conclusion.model_dump(mode="json"),
                        "validated_findings": [
                            {"statement": statement.model_dump(mode="json"),
                             "attribution": by_id[statement.statement_id].model_dump(mode="json")}
                            for statement in decision.statements
                            if statement.statement_id in decision.conclusion.based_on_statement_ids
                        ],
                    }, judge_run_id=str(judge.judge_run_id),
                    validation_run_id=str(validation_id),
                    statement_ids=decision.conclusion.based_on_statement_ids,
                    evidence_ids=conclusion_ids,
                )
                prompt_hashes.append(semantic.prompt_hash)
                calls += 1
                try:
                    async with asyncio.timeout(18.0):
                        response = await validator.assess_conclusion(semantic)
                    if (response.based_on_statement_ids != semantic.statement_ids
                            or response.evidence_ids != semantic.evidence_ids):
                        raise ValueError("semantic conclusion references differ from request")
                    issues = ((_issue(IssueCode.CONCLUSION_NOT_JUSTIFIED, "conclusion",
                                      conclusion_ids),)
                              if response.status == ConclusionJustificationStatus.NOT_JUSTIFIED
                              else ())
                    conclusion = ConclusionJustification(
                        status=response.status,
                        based_on_statement_ids=response.based_on_statement_ids,
                        evidence_ids=response.evidence_ids, reason=response.reason,
                        issues=issues, validator_provenance={
                            "provider": validator.provider, "model": validator.model,
                            "prompt_version": PROMPT_VERSION,
                            "prompt_hash": semantic.prompt_hash,
                        },
                    )
                except Exception:
                    error_category = "conclusion_validator_unavailable"
                    conclusion = ConclusionJustification(
                        status=ConclusionJustificationStatus.UNABLE_TO_ASSESS,
                        based_on_statement_ids=decision.conclusion.based_on_statement_ids,
                        evidence_ids=conclusion_ids,
                        reason="Conclusion semantic validation was unavailable.",
                    )
    except TimeoutError:
        error_category = "validation_deadline_exceeded"
        attributions = ()
        conclusion = ConclusionJustification(
            status=ConclusionJustificationStatus.UNABLE_TO_ASSESS,
            based_on_statement_ids=decision.conclusion.based_on_statement_ids,
            evidence_ids=(), reason="Validation deadline was exceeded.",
        )

    targeted = tuple(issue for item in attributions for issue in item.issues) + conclusion.issues
    if unit_contract and attributions and decision.schema_version not in {"2.3", "2.4", "2.5"}:
        dependency_ids = set(decision.conclusion.based_on_statement_ids)
        source_texts = tuple(ref.quote for statement in decision.statements
                             if statement.statement_id in dependency_ids
                             for ref in statement.evidence_refs)
        check = compare_assertion_numbers(
            decision.conclusion.justification,
            source_texts,
                                          user_claim=pack.claim_snapshot.standalone_text)
        if check.status in {NumericAlignment.MISMATCH, NumericAlignment.UNCERTAIN}:
            issue = _issue(
                IssueCode.STATEMENT_NUMERIC_MISMATCH if check.status == NumericAlignment.MISMATCH
                else IssueCode.NUMERIC_UNCERTAIN, "conclusion", conclusion.evidence_ids,
                observed=decision.conclusion.justification,
                measure=check.asserted.kind if check.asserted else "unclassified",
                severity="fatal" if check.status == NumericAlignment.MISMATCH else "warning",
            ).model_copy(update={"numeric_diagnostic": check.diagnostic(),
                                 "conclusion_dependency": True})
            targeted += (issue,)
            if qualification_audit is not None:
                revised_input = qualification_audit.input.model_copy(update={
                    "defects": (*qualification_audit.input.defects, issue),
                })
                revised_output = qualify_conclusion(revised_input)
                qualification_audit = ConclusionQualificationAudit(
                    input=revised_input, output=revised_output,
                )
                conclusion = conclusion.model_copy(update={
                    "status": (ConclusionJustificationStatus.UNABLE_TO_ASSESS
                               if relation_audit and relation_audit.error_category
                               else revised_output.status),
                    "reason": "; ".join(revised_output.reason_codes),
                    "issues": (*conclusion.issues, issue),
                })
            else:
                conclusion = conclusion.model_copy(update={
                    "status": ConclusionJustificationStatus.UNCERTAIN,
                    "issues": (*conclusion.issues, issue),
                })
    fatal = tuple(dict.fromkeys(issue.issue_code for issue in targeted
                                if issue.severity == "fatal"))
    warnings = tuple(dict.fromkeys(issue.issue_code for issue in targeted
                                   if issue.severity == "warning"))
    if fatal:
        status = ValidationStatus.INVALID
    elif (conclusion.status == ConclusionJustificationStatus.JUSTIFIED
          and len(attributions) == len(decision.statements)
          and all(item.status == StatementAttributionStatus.SUPPORTED_BY_SOURCES
                  for item in attributions)
          and not warnings):
        status = ValidationStatus.VALIDATED
    elif conclusion.status == ConclusionJustificationStatus.JUSTIFIED:
        status = ValidationStatus.PARTIALLY_VALIDATED
    else:
        status = ValidationStatus.UNABLE_TO_VALIDATE
    result = JudgeValidationResult(
        judge_run_id=judge.judge_run_id, evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=judge.evidence_pack_hash, judge_label=decision.label,
        citation_validations=(), opposing_citation_validations=(),
        validation_status=status, fatal_issue_codes=fatal, warnings=warnings,
        validation_version=validation_version, statement_attributions=attributions,
        conclusion_justification=conclusion, targeted_issues=targeted,
        relation_validation=relation_audit.model_dump(mode="json") if relation_audit else None,
        conclusion_qualification=(qualification_audit.model_dump(mode="json")
                                  if qualification_audit else None),
    )
    aggregate_hash = (hashlib.sha256("".join(sorted(prompt_hashes)).encode()).hexdigest()
                      if prompt_hashes else None)
    return JudgeValidationRun(
        id=validation_id, judge_run_id=judge.judge_run_id,
        evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=judge.evidence_pack_hash,
        validation_version=validation_version,
        deterministic_validator_version=("source-unit-assertion-numeric-2.1+conclusion-qualifier-1.0"
                                         if relation_contract else
                                         "source-unit-assertion-numeric-2.1") if unit_contract
        else DETERMINISTIC_VERSION,
        entailment_provider=validator.provider if validator else None,
        entailment_model=validator.model if validator else None,
        prompt_version=PROMPT_VERSION if prompt_hashes else None,
        prompt_hash=aggregate_hash, started_at=started_at,
        completed_at=datetime.now(UTC), status=status, result=result,
        error_category=error_category,
        latency_ms=round((monotonic() - start) * 1000), attempt_count=calls,
    )
