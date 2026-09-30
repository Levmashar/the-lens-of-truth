"""Statement attribution, then conclusion justification, on frozen judge input."""

import asyncio
import hashlib
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from app.judging.models import JudgeDecisionV2, JudgeRun
from app.judging.prompt import (
    INPUT_SNAPSHOT_VERSION,
    input_snapshot_hash,
    prepare_judge_input,
)
from app.retrieval.models import EvidencePack
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
    *, timeout_seconds: float = 45.0,
) -> JudgeValidationRun:
    decision = judge.decision
    if not isinstance(decision, JudgeDecisionV2):
        raise ValueError("V2 validation requires a V2 decision")
    started_at, start = datetime.now(UTC), monotonic()
    validation_id = uuid4()
    prepared = prepare_judge_input(judge.evidence_pack_id, pack)
    snapshot_valid = (
        judge.input_snapshot_version == INPUT_SNAPSHOT_VERSION
        and judge.input_snapshot_hash == prepared.input_snapshot_hash
        and judge.input_snapshot_json is not None
        and input_snapshot_hash(judge.input_snapshot_json) == prepared.input_snapshot_hash
        and judge.evidence_pack_hash == pack.snapshot_hash
        and judge.claim_id == pack.claim_id
    )
    passage_map = {item.evidence_id: item for item in pack.passages}
    document_map = {item.document_id: item for item in pack.documents}
    visible = set(prepared.selected_ids) if snapshot_valid else set()
    calls = 0
    prompt_hashes: list[str] = []
    error_category: str | None = None

    async def one_statement(statement: object) -> StatementAttribution:
        nonlocal calls, error_category
        assert isinstance(statement, type(decision.statements[0]))
        ids = tuple(ref.evidence_id for ref in statement.evidence_refs)
        issues: list[ValidationIssue] = []
        frozen: list[dict[str, object]] = []
        quotes: list[str] = []
        if not snapshot_valid:
            issues.append(_issue(IssueCode.PACK_HASH_MISMATCH, statement.statement_id, ids))
        for ref in statement.evidence_refs:
            item = passage_map.get(ref.evidence_id)
            document = document_map.get(item.passage.document_id) if item else None
            if item is None or ref.evidence_id not in visible:
                issues.append(_issue(IssueCode.CITATION_NOT_SELECTED,
                                     statement.statement_id, (ref.evidence_id,)))
                continue
            if document is None or not document.pmid or not document.canonical_url:
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
            })
        if not issues:
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
            bad_dependency = any(
                item.status != StatementAttributionStatus.SUPPORTED_BY_SOURCES
                or any(issue.severity == "fatal" for issue in item.issues)
                for item in dependencies
            )
            if unavailable_dependency:
                conclusion = ConclusionJustification(
                    status=ConclusionJustificationStatus.UNABLE_TO_ASSESS,
                    based_on_statement_ids=decision.conclusion.based_on_statement_ids,
                    evidence_ids=conclusion_ids,
                    reason="A required statement assessment was unavailable.",
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
            elif (decision.label.value != "not_enough_evidence"
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
        validation_version=VALIDATION_VERSION, statement_attributions=attributions,
        conclusion_justification=conclusion, targeted_issues=targeted,
    )
    aggregate_hash = (hashlib.sha256("".join(sorted(prompt_hashes)).encode()).hexdigest()
                      if prompt_hashes else None)
    return JudgeValidationRun(
        id=validation_id, judge_run_id=judge.judge_run_id,
        evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=judge.evidence_pack_hash,
        validation_version=VALIDATION_VERSION,
        deterministic_validator_version=DETERMINISTIC_VERSION,
        entailment_provider=validator.provider if validator else None,
        entailment_model=validator.model if validator else None,
        prompt_version=PROMPT_VERSION if prompt_hashes else None,
        prompt_hash=aggregate_hash, started_at=started_at,
        completed_at=datetime.now(UTC), status=status, result=result,
        error_category=error_category,
        latency_ms=round((monotonic() - start) * 1000), attempt_count=calls,
    )
