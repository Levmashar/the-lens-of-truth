"""Phase 6B deterministic, offline decision table and release-gate regressions."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.judging.models import JudgeLabel, JudgeRun
from app.retrieval.evidence_pack import build_evidence_pack
from app.validation.models import (
    CitationValidation,
    EntailmentStatus,
    IssueCode,
    JudgeValidationResult,
    JudgeValidationRun,
    NumericAlignment,
    RelationAlignment,
    ScopeAlignment,
    ValidationStatus,
)
from app.verdict.models import (
    AggregationContext,
    AggregationInput,
    AggregationMode,
    ClaimFacts,
    LensVerdict,
    ReasonCode,
)
from app.verdict.policy import POLICY_V1
from app.verdict.service import VerdictService
from tests.test_validation import fixture_pack, judge_for

NOW = datetime(2026, 9, 28, tzinfo=UTC)


def validation_for(
    judge: JudgeRun, *, status: ValidationStatus = ValidationStatus.VALIDATED,
    provider: str = "fixture", fatal: tuple[IssueCode, ...] = (),
) -> JudgeValidationRun:
    assert judge.decision is not None

    def citation(evidence_id: str, role: str) -> CitationValidation:
        return CitationValidation(
            evidence_id=evidence_id, role=role, exists=True,
            selected_for_judging=True, passage_hash_matches=True,
            document_provenance_exists=True, integrity_status="valid",
            numeric_alignment=NumericAlignment.ALIGNED,
            scope_alignment=ScopeAlignment.ALIGNED,
            relation_alignment=RelationAlignment.ALIGNED,
            entailment_status=EntailmentStatus.ENTAILS_JUDGE_USE,
            issue_codes=fatal if role == "cited" else (),
        )

    result = JudgeValidationResult(
        judge_run_id=judge.judge_run_id, evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=judge.evidence_pack_hash, judge_label=judge.decision.label,
        citation_validations=tuple(citation(eid, "cited")
                                   for eid in judge.decision.cited_evidence_ids),
        opposing_citation_validations=tuple(citation(eid, "opposing")
                                            for eid in judge.decision.opposing_evidence_ids),
        validation_status=status, fatal_issue_codes=fatal, warnings=(),
        validation_version=POLICY_V1.validation_version,
    )
    return JudgeValidationRun(
        id=uuid4(), judge_run_id=judge.judge_run_id,
        evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=judge.evidence_pack_hash,
        validation_version=POLICY_V1.validation_version,
        deterministic_validator_version="fixture", entailment_provider=provider,
        entailment_model="fixture", prompt_version="fixture", prompt_hash="f" * 64,
        started_at=NOW, completed_at=NOW, status=status, result=result,
        error_category=None, latency_ms=0, attempt_count=1,
    )


def case(
    labels: tuple[JudgeLabel | None, ...], *, risk: str = "standard",
    mode: AggregationMode = AggregationMode.FIXTURE_OR_EVALUATION,
    invalid: frozenset[int] = frozenset(),
    partial: frozenset[int] = frozenset(),
    unvalidated: frozenset[int] = frozenset(),
    miri: bool = False,
) -> tuple[AggregationInput, AggregationContext]:
    pack = fixture_pack()
    pack_id = uuid4()
    judges: list[JudgeRun] = []
    validations: list[JudgeValidationRun] = []
    for index, label in enumerate(labels, start=1):
        base = judge_for(pack, label=label or JudgeLabel.SUPPORTED)
        decision = base.decision if label is not None else None
        judge = base.model_copy(update={
            "evidence_pack_id": pack_id, "slot": index,
            "model": f"fixture-{index}", "model_family": f"family-{index}",
            "model_snapshot": f"snapshot-{index}",
            "model_identity_verified": True, "model_family_verified": True,
            "search_isolation_verified": not miri,
            "search_override_active": miri, "search_guard_bypassed": miri,
            "decision": decision,
            "response_json": decision.model_dump(mode="json") if decision else None,
            "outcome_status": "failed" if label is None else "succeeded",
        })
        judges.append(judge)
        if label is not None and index not in unvalidated:
            status = (ValidationStatus.INVALID if index in invalid
                      else ValidationStatus.PARTIALLY_VALIDATED if index in partial
                      else ValidationStatus.VALIDATED)
            fatal = ((IssueCode.MATERIAL_NUMERIC_MISMATCH,)
                     if index in invalid else ())
            validations.append(validation_for(judge, status=status, fatal=fatal))
    request = AggregationInput(
        claim_id=pack.claim_id, evidence_pack_id=pack_id,
        evidence_pack_hash=pack.snapshot_hash,
        judge_run_ids=tuple(item.judge_run_id for item in judges),
        judge_validation_run_ids=tuple(item.id for item in validations),
        mode=mode, policy_version=POLICY_V1.version,
    )
    context = AggregationContext(
        claim=ClaimFacts(claim_id=pack.claim_id, risk_class=risk,
                         normalization_status="normalized"),
        pack=pack, stored_pack_hash=pack.snapshot_hash,
        retrieval_status="ok", judges=tuple(judges),
        validations=tuple(validations),
    )
    return request, context


S = JudgeLabel.SUPPORTED
C = JudgeLabel.CONTRADICTED
N = JudgeLabel.NOT_ENOUGH_EVIDENCE


@pytest.mark.parametrize(("labels", "risk", "expected"), [
    ((S, S, S), "standard", LensVerdict.SUPPORTED),
    ((S, S, N), "standard", LensVerdict.SUPPORTED),
    ((C, C, N), "standard", LensVerdict.CONTRADICTED),
    ((S, S, C), "standard", LensVerdict.NOT_ENOUGH_EVIDENCE),
    ((S, N, N), "standard", LensVerdict.NOT_ENOUGH_EVIDENCE),
    ((N, N, N), "standard", LensVerdict.NOT_ENOUGH_EVIDENCE),
    ((S, C, N), "standard", LensVerdict.NOT_ENOUGH_EVIDENCE),
    ((S, S, S), "high", LensVerdict.SUPPORTED),
    ((S, S, N), "high", LensVerdict.NOT_ENOUGH_EVIDENCE),
    ((C, C, C), "high", LensVerdict.CONTRADICTED),
    ((C, C, N), "high", LensVerdict.NOT_ENOUGH_EVIDENCE),
    ((S, S, C), "high", LensVerdict.NOT_ENOUGH_EVIDENCE),
])
def test_offline_decision_table(
    labels: tuple[JudgeLabel, ...], risk: str, expected: LensVerdict,
) -> None:
    request, context = case(labels, risk=risk)
    result = VerdictService().aggregate(request, context)
    assert result.verdict == expected
    assert result.qualified_judges == 3
    assert not result.production_qualified
    assert ReasonCode.EVALUATION_ONLY in result.reason_codes


def test_only_one_qualified_is_system_inability() -> None:
    request, context = case((S, None, None))
    result = VerdictService().aggregate(request, context)
    assert result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.INSUFFICIENT_QUALIFIED_JUDGES in result.reason_codes
    assert result.validated_label_counts[S] == 1


def test_inferred_protocol_version_never_qualifies_in_production() -> None:
    request, context = case((S, S), mode=AggregationMode.PRODUCTION)
    first = context.judges[0].model_copy(update={"schema_version_inferred": True})
    context = context.model_copy(update={"judges": (first, context.judges[1])})
    result = VerdictService().aggregate(request, context)
    assert any(
        item.judge_run_id == first.judge_run_id
        and ReasonCode.AUDIT_RECORD_INVALID in item.exclusion_reasons
        for item in result.judge_qualifications
    )


def test_required_validation_unavailable_is_system_inability() -> None:
    request, context = case((S, S), unvalidated=frozenset({2}))
    result = VerdictService().aggregate(request, context)
    assert result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.VALIDATION_UNAVAILABLE in result.reason_codes


def test_partial_scope_can_validate_only_an_evaluation_inconclusive_use() -> None:
    request, context = case((N, N), partial=frozenset({1, 2}))
    validations = tuple(item.model_copy(update={
        "result": item.result.model_copy(update={
            "warnings": (IssueCode.PARTIAL_SCOPE_MATCH,),
            "citation_validations": tuple(citation.model_copy(update={
                "scope_alignment": ScopeAlignment.PARTIAL,
                "warnings": (IssueCode.PARTIAL_SCOPE_MATCH,),
            }) for citation in item.result.citation_validations),
        }),
    }) for item in context.validations)
    context = context.model_copy(update={"validations": validations})
    evaluation = VerdictService().aggregate(request, context)
    assert evaluation.verdict == LensVerdict.NOT_ENOUGH_EVIDENCE
    assert evaluation.qualified_judges == 2
    assert not evaluation.production_qualified

    production = VerdictService().aggregate(
        request.model_copy(update={"mode": AggregationMode.PRODUCTION}), context,
    )
    assert production.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert all(ReasonCode.VALIDATION_PARTIAL in item.exclusion_reasons
               for item in production.judge_qualifications)

    decisive_request, decisive_context = case((S, S), partial=frozenset({1, 2}))
    decisive = VerdictService().aggregate(decisive_request, decisive_context)
    assert decisive.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY


def test_no_results_is_evidence_insufficiency_not_technical_failure() -> None:
    request, context = case(())
    assert context.pack is not None
    empty = build_evidence_pack(
        context.pack.claim_snapshot, context.pack.query_plan, (), (), retrieved_at=NOW,
    )
    request = request.model_copy(update={"evidence_pack_hash": empty.snapshot_hash})
    context = context.model_copy(update={
        "pack": empty, "stored_pack_hash": empty.snapshot_hash,
        "retrieval_status": "no_results",
    })
    result = VerdictService().aggregate(request, context)
    assert result.verdict == LensVerdict.NOT_ENOUGH_EVIDENCE
    assert ReasonCode.RETRIEVAL_NO_RESULTS in result.reason_codes


def test_retrieval_failure_is_system_inability() -> None:
    request, context = case((S, S))
    context = context.model_copy(update={"retrieval_status": "technical_failure"})
    result = VerdictService().aggregate(request, context)
    assert result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.RETRIEVAL_TECHNICAL_FAILURE in result.reason_codes


def test_pack_hash_mismatch_cannot_be_voted_around() -> None:
    request, context = case((S, S, S))
    request = request.model_copy(update={"evidence_pack_hash": "0" * 64})
    result = VerdictService().aggregate(request, context)
    assert result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert result.reason_codes[0] == ReasonCode.PACK_HASH_MISMATCH


def test_current_miri_style_smoke_cannot_qualify_for_production() -> None:
    request, context = case((C, C, None), mode=AggregationMode.PRODUCTION, miri=True)
    result = VerdictService().aggregate(request, context)
    assert result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert not result.production_qualified
    assert ReasonCode.SEARCH_ISOLATION_UNVERIFIED in result.reason_codes
    assert ReasonCode.INSUFFICIENT_QUALIFIED_JUDGES in result.reason_codes
    evaluation = VerdictService().aggregate(
        request.model_copy(update={"mode": AggregationMode.FIXTURE_OR_EVALUATION}),
        context,
    )
    assert evaluation.verdict == LensVerdict.CONTRADICTED
    assert not evaluation.production_qualified
    assert ReasonCode.EVALUATION_ONLY in evaluation.reason_codes


@pytest.mark.parametrize(("risk", "expected"), [
    ("standard", LensVerdict.SUPPORTED),
    ("high", LensVerdict.UNABLE_TO_VERIFY_RELIABLY),
])
def test_invalid_supported_never_counts(
    risk: str, expected: LensVerdict,
) -> None:
    request, context = case((S, S, S), risk=risk, invalid=frozenset({3}))
    result = VerdictService().aggregate(request, context)
    assert result.verdict == expected
    assert result.validated_label_counts[S] == 2
    assert result.excluded_judges == 1
    assert ReasonCode.VALIDATION_FATAL_ISSUE in result.reason_codes


def test_invalid_opposing_label_does_not_create_validated_disagreement() -> None:
    request, context = case((S, S, C), invalid=frozenset({3}))
    result = VerdictService().aggregate(request, context)
    assert result.verdict == LensVerdict.SUPPORTED
    assert not result.conflicting_decisive_labels
    assert result.validated_label_counts[C] == 0


def test_partial_judge_does_not_supply_decisive_threshold() -> None:
    request, context = case((S, S, N), partial=frozenset({2}))
    result = VerdictService().aggregate(request, context)
    assert result.verdict == LensVerdict.NOT_ENOUGH_EVIDENCE
    assert result.validated_label_counts[S] == 1
    assert ReasonCode.VALIDATION_PARTIAL in result.reason_codes


def test_production_requires_approved_entailment_even_with_verified_models() -> None:
    request, context = case((S, S), mode=AggregationMode.PRODUCTION)
    result = VerdictService().aggregate(request, context)
    assert result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.VALIDATION_PROVIDER_UNAPPROVED in result.reason_codes
    approved = replace(POLICY_V1, approved_entailment_providers=frozenset({"fixture"}))
    qualified = VerdictService(approved).aggregate(request, context)
    assert qualified.verdict == LensVerdict.SUPPORTED
    assert qualified.production_qualified


def test_explicit_ids_and_pack_identity_are_required() -> None:
    request, context = case((S, S))
    missing = request.model_copy(update={"judge_validation_run_ids": ()})
    assert VerdictService().aggregate(missing, context).verdict == (
        LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    )
    wrong = context.model_copy(update={
        "judges": (context.judges[0].model_copy(update={"evidence_pack_id": uuid4()}),
                   context.judges[1]),
    })
    assert ReasonCode.AUDIT_RECORD_MISMATCH in (
        VerdictService().aggregate(request, wrong).reason_codes
    )


def test_same_inputs_have_same_semantic_hash_and_changed_validation_changes_it() -> None:
    request, context = case((S, S, N))
    first = VerdictService().aggregate(request, context)
    second = VerdictService().aggregate(request, context)
    assert first == second
    assert first.semantic_hash == second.semantic_hash
    reordered = AggregationInput(
        claim_id=request.claim_id, evidence_pack_id=request.evidence_pack_id,
        evidence_pack_hash=request.evidence_pack_hash,
        judge_run_ids=tuple(reversed(request.judge_run_ids)),
        judge_validation_run_ids=tuple(reversed(request.judge_validation_run_ids)),
        mode=request.mode, policy_version=request.policy_version,
    )
    assert VerdictService().aggregate(reordered, context).semantic_hash == first.semantic_hash
    changed = context.model_copy(update={
        "validations": (context.validations[0].model_copy(update={
            "status": ValidationStatus.PARTIALLY_VALIDATED,
            "result": context.validations[0].result.model_copy(update={
                "validation_status": ValidationStatus.PARTIALLY_VALIDATED,
            }),
        }), *context.validations[1:]),
    })
    different = VerdictService().aggregate(request, changed)
    assert different.semantic_hash != first.semantic_hash


def test_unknown_policy_and_duplicate_ids_fail_closed() -> None:
    request, context = case((S, S))
    with pytest.raises(ValueError, match="Unsupported verdict policy"):
        VerdictService().aggregate(request.model_copy(update={"policy_version": "unknown"}),
                                   context)
    with pytest.raises(ValueError, match="Duplicate judge run IDs"):
        AggregationInput(
            claim_id=request.claim_id, evidence_pack_id=request.evidence_pack_id,
            evidence_pack_hash=request.evidence_pack_hash,
            judge_run_ids=(UUID(int=1), UUID(int=1)), judge_validation_run_ids=(),
            mode=AggregationMode.PRODUCTION, policy_version=POLICY_V1.version,
        )


@pytest.mark.parametrize(("change", "reason"), [
    ({"claim": None}, ReasonCode.CLAIM_UNAVAILABLE),
    ({"retrieval_status": None}, ReasonCode.RETRIEVAL_TECHNICAL_FAILURE),
    ({"pack": None}, ReasonCode.PACK_UNAVAILABLE),
    ({"stored_pack_hash": "0" * 64}, ReasonCode.PACK_HASH_MISMATCH),
])
def test_pipeline_preconditions_fail_before_labels(
    change: dict[str, object], reason: ReasonCode,
) -> None:
    request, context = case((S, S, S))
    result = VerdictService().aggregate(request, context.model_copy(update=change))
    assert result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert reason in result.reason_codes
    assert result.qualified_judges == 0


def test_incomplete_normalization_is_not_evidence_insufficiency() -> None:
    request, context = case((N, N, N))
    assert context.claim is not None
    context = context.model_copy(update={
        "claim": context.claim.model_copy(update={"normalization_status": "partial"}),
    })
    result = VerdictService().aggregate(request, context)
    assert result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.NORMALIZATION_INCOMPLETE in result.reason_codes


def test_complete_pico_with_partial_terminology_can_be_evaluated() -> None:
    request, context = case((S, S, S))
    assert context.claim is not None
    context = context.model_copy(update={
        "claim": context.claim.model_copy(update={
            "normalization_status": "partially_linked", "normalization_reviewed": True,
        }),
    })

    result = VerdictService().aggregate(request, context)

    assert ReasonCode.NORMALIZATION_INCOMPLETE not in result.reason_codes


def test_unaudited_partial_terminology_fails_verdict_closed() -> None:
    request, context = case((S, S, S))
    assert context.claim is not None
    context = context.model_copy(update={
        "claim": context.claim.model_copy(update={
            "normalization_status": "partially_linked", "normalization_reviewed": False,
        }),
    })

    result = VerdictService().aggregate(request, context)

    assert result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.NORMALIZATION_INCOMPLETE in result.reason_codes


def test_duplicate_model_family_does_not_count_as_independent_judge() -> None:
    request, context = case((S, S))
    judges = (context.judges[0], context.judges[1].model_copy(update={
        "model_family": context.judges[0].model_family,
    }))
    result = VerdictService().aggregate(
        request, context.model_copy(update={"judges": judges}),
    )
    assert result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.DUPLICATE_MODEL_FAMILY in result.reason_codes


def test_validation_result_label_must_match_the_exact_judge() -> None:
    request, context = case((S, S))
    changed = context.validations[0].model_copy(update={
        "result": context.validations[0].result.model_copy(update={
            "judge_label": JudgeLabel.CONTRADICTED,
        }),
    })
    result = VerdictService().aggregate(
        request, context.model_copy(update={
            "validations": (changed, *context.validations[1:]),
        }),
    )
    assert result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.AUDIT_RECORD_MISMATCH in result.reason_codes
