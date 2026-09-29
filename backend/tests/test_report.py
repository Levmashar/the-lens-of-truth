"""Phase 6C offline presentation regressions; fixture labels are not medical truth."""

import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.judging.models import JudgeLabel
from app.main import create_app
from app.pipeline.claim_types import ClaimType
from app.report.builder import (
    DISPLAY_LABELS,
    REASON_TEXT,
    build_report,
    semantic_report_hash,
)
from app.report.models import EvidenceRole, EvidenceState, LensReport
from app.report.smoke import format_report
from app.retrieval.evidence_pack import build_evidence_pack
from app.validation.models import IssueCode, RelationAlignment, ScopeAlignment
from app.verdict.models import AggregationContext, AggregationInput, LensVerdict, ReasonCode
from app.verdict.service import VerdictService, semantic_result_hash
from tests.test_verdict import NOW, C, N, S, case


def report_for(
    labels: tuple[JudgeLabel | None, ...], *, invalid: frozenset[int] = frozenset(),
    partial: frozenset[int] = frozenset(),
    miri: bool = False,
) -> tuple[LensReport, AggregationInput, AggregationContext]:
    request, context = case(labels, invalid=invalid, partial=partial, miri=miri)
    assert context.pack is not None
    verdict = VerdictService().aggregate(request, context)
    report = build_report(uuid4(), verdict, context.pack, context.judges,
                          context.validations, generated_at=NOW)
    return report, request, context


@pytest.mark.parametrize(("labels", "expected", "role"), [
    ((S, S), LensVerdict.SUPPORTED, EvidenceRole.SUPPORTING),
    ((C, C), LensVerdict.CONTRADICTED, EvidenceRole.OPPOSING),
    ((S, C), LensVerdict.NOT_ENOUGH_EVIDENCE, EvidenceRole.SUPPORTING),
    ((S, None), LensVerdict.UNABLE_TO_VERIFY_RELIABLY, None),
])
def test_four_exact_labels_and_source_roles(
    labels: tuple[JudgeLabel | None, ...], expected: LensVerdict,
    role: EvidenceRole | None,
) -> None:
    report, _, context = report_for(labels)
    assert report.verdict == expected
    assert report.verdict_display == DISPLAY_LABELS[expected]
    assert report.verdict_display in {
        "Supported", "Contradicted", "Not Enough Evidence", "Unable to Verify Reliably",
    }
    assert report.production_qualified is False
    assert report.verification_status.development_notice
    assert context.pack is not None
    assert report.claim.text == context.pack.claim_snapshot.raw_text
    assert report.safety_notice
    if role is None:
        assert not report.key_evidence
    else:
        assert report.key_evidence
        assert role in report.key_evidence[0].evidence_roles
        if expected == LensVerdict.NOT_ENOUGH_EVIDENCE:
            assert EvidenceRole.OPPOSING in report.key_evidence[0].evidence_roles
    assert not any("confidence" in key for key in report.model_dump())


def test_controlled_reason_mapping_is_total_and_deterministic() -> None:
    assert set(REASON_TEXT) == set(ReasonCode)
    report, _, _ = report_for((S, S))
    assert tuple(item.text for item in report.why_this_result) == tuple(
        REASON_TEXT[item.code] for item in report.why_this_result
    )
    assert any(item.code == ReasonCode.SUPPORTED_BY_MULTIPLE_VALIDATED_JUDGES
               for item in report.why_this_result)


def test_source_cards_are_exact_frozen_cited_passages_only() -> None:
    report, _, context = report_for((S, S))
    assert context.pack is not None
    selected = set(context.pack.selected_evidence_ids)
    passages = {item.evidence_id: item for item in context.pack.passages}
    documents = {item.document_id: item for item in context.pack.documents}
    for card in report.key_evidence:
        assert card.evidence_id in selected
        passage = passages[card.evidence_id].passage
        document = documents[passage.document_id]
        assert card.exact_excerpt == passage.text[:600]
        assert card.passage_sha256 == passage.content_sha256
        assert card.pmid == document.pmid
        assert card.source_url == document.canonical_url
        assert card.citation_validated
        assert card.cited_by_validation_run_ids
    assert {item.evidence_id for item in report.sources} == {
        item.evidence_id for item in report.key_evidence
    }


def test_unknown_citation_is_never_presented() -> None:
    request, context = case((S, S))
    assert context.pack is not None
    first = context.validations[0]
    citation = first.result.citation_validations[0].model_copy(update={
        "evidence_id": "E999",
    })
    changed = first.model_copy(update={"result": first.result.model_copy(update={
        "citation_validations": (citation,),
    })})
    context = context.model_copy(update={"validations": (changed, *context.validations[1:])})
    verdict = VerdictService().aggregate(request, context)
    assert verdict.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    report = build_report(uuid4(), verdict, context.pack, context.judges,
                          context.validations, generated_at=NOW)
    assert not report.key_evidence


def test_disagreement_and_insufficient_evidence_are_distinct() -> None:
    disagree, _, _ = report_for((S, C, N))
    assert disagree.verdict == LensVerdict.NOT_ENOUGH_EVIDENCE
    assert disagree.verification_status.evidence_state == EvidenceState.CONFLICTING
    assert "disagreed" in disagree.short_summary
    assert "confidence" not in disagree.judge_summary.description.lower()
    insufficient, _, _ = report_for((N, N))
    assert insufficient.verdict == LensVerdict.NOT_ENOUGH_EVIDENCE
    assert insufficient.verification_status.evidence_state == (
        EvidenceState.RELEVANT_BUT_INSUFFICIENT
    )
    assert "disagreed" not in insufficient.short_summary
    assert all(EvidenceRole.RELEVANT_BUT_INSUFFICIENT in item.evidence_roles
               for item in insufficient.key_evidence)


def test_evaluation_inconclusive_shows_validated_limited_source() -> None:
    request, context = case((N, N), partial=frozenset({1, 2}))
    assert context.pack is not None
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
    verdict = VerdictService().aggregate(request, context)
    report = build_report(uuid4(), verdict, context.pack, context.judges,
                          context.validations, generated_at=NOW)
    assert report.verdict == LensVerdict.NOT_ENOUGH_EVIDENCE
    assert not report.production_qualified
    assert report.key_evidence
    assert all(EvidenceRole.RELEVANT_BUT_INSUFFICIENT in card.evidence_roles
               for card in report.key_evidence)


def test_excluded_judge_is_visible_without_brand_rankings() -> None:
    report, _, _ = report_for((S, S, C), invalid=frozenset({3}))
    assert report.verdict == LensVerdict.SUPPORTED
    assert report.judge_summary.excluded == 1
    assert len(report.judge_summary.excluded_assessments) == 1
    assert "family-" not in format_report(report, uuid4())
    assert "fixture-" not in format_report(report, uuid4())


def test_retrieval_technical_failure_has_no_fake_cards() -> None:
    request, context = case((S, S))
    assert context.pack is not None
    context = context.model_copy(update={"retrieval_status": "technical_failure"})
    verdict = VerdictService().aggregate(request, context)
    report = build_report(uuid4(), verdict, context.pack, context.judges,
                          context.validations, generated_at=NOW)
    assert report.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert report.verification_status.evidence_state == EvidenceState.VERIFICATION_INCOMPLETE
    assert not report.key_evidence
    assert any(item.code == ReasonCode.RETRIEVAL_TECHNICAL_FAILURE
               for item in report.why_this_result)
    assert "conflicts with this claim" not in report.short_summary


def test_no_results_is_not_no_research_claim() -> None:
    request, context = case(())
    assert context.pack is not None
    empty = build_evidence_pack(
        context.pack.claim_snapshot, context.pack.query_plan, (), (), retrieved_at=NOW,
    )
    request = request.model_copy(update={"evidence_pack_hash": empty.snapshot_hash})
    context = context.model_copy(update={"pack": empty,
                                         "stored_pack_hash": empty.snapshot_hash,
                                         "retrieval_status": "no_results"})
    verdict = VerdictService().aggregate(request, context)
    report = build_report(uuid4(), verdict, empty, (), (), generated_at=NOW)
    assert report.verdict == LensVerdict.NOT_ENOUGH_EVIDENCE
    assert report.verification_status.evidence_state == EvidenceState.NO_RESULTS
    assert not report.key_evidence
    assert "no research" not in report.short_summary.lower()


def test_numeric_causal_and_scope_failures_surface_without_unsupported_number() -> None:
    request, context = case((C, C, C), invalid=frozenset({3}))
    assert context.pack is not None
    snapshot = context.pack.claim_snapshot.model_copy(update={
        "raw_text": "Treatment X causes a 292% increase in Y in adults.",
        "claim_type": ClaimType.CAUSAL,
    })
    pack = build_evidence_pack(snapshot, context.pack.query_plan, context.pack.documents,
                               context.pack.passages, retrieved_at=NOW)
    judges = tuple(item.model_copy(update={"evidence_pack_hash": pack.snapshot_hash})
                   for item in context.judges)
    validations = []
    for item in context.validations:
        result = item.result.model_copy(update={"evidence_pack_hash": pack.snapshot_hash})
        if item.judge_run_id == context.judges[2].judge_run_id:
            citation = result.citation_validations[0].model_copy(update={
                "issue_codes": (
                    IssueCode.MATERIAL_NUMERIC_MISMATCH,
                    IssueCode.RELATION_STRENGTH_MISMATCH,
                    IssueCode.MATERIAL_SCOPE_MISMATCH,
                ),
                "relation_alignment": RelationAlignment.WEAKER_THAN_CLAIM,
            })
            result = result.model_copy(update={
                "citation_validations": (citation,),
                "fatal_issue_codes": citation.issue_codes,
            })
        validations.append(item.model_copy(update={
            "evidence_pack_hash": pack.snapshot_hash, "result": result,
        }))
    request = request.model_copy(update={"evidence_pack_hash": pack.snapshot_hash})
    context = context.model_copy(update={
        "pack": pack, "stored_pack_hash": pack.snapshot_hash,
        "judges": judges, "validations": tuple(validations),
    })
    verdict = VerdictService().aggregate(request, context)
    assert verdict.verdict == LensVerdict.CONTRADICTED
    report = build_report(uuid4(), verdict, pack, judges, tuple(validations), generated_at=NOW)
    assert len(report.evidence_limitations) >= 3
    assert any("numerical magnitude" in item for item in report.evidence_limitations)
    assert any("Association does not by itself establish causation" in item
               for item in report.evidence_limitations)
    assert any("materially different" in item for item in report.evidence_limitations)
    assert "292%" not in report.short_summary


def test_retracted_source_is_not_validated_positive_evidence() -> None:
    request, context = case((S, S))
    assert context.pack is not None
    document = context.pack.documents[0]
    changed = document.model_copy(update={
        "integrity": document.integrity.model_copy(update={"status": "retracted"}),
    })
    pack = build_evidence_pack(context.pack.claim_snapshot, context.pack.query_plan,
                               (changed,), context.pack.passages, retrieved_at=NOW)
    request = request.model_copy(update={"evidence_pack_hash": pack.snapshot_hash})
    judges = tuple(item.model_copy(update={"evidence_pack_hash": pack.snapshot_hash})
                   for item in context.judges)
    validations = tuple(item.model_copy(update={
        "evidence_pack_hash": pack.snapshot_hash,
    }) for item in context.validations)
    verdict = VerdictService().aggregate(request, context.model_copy(update={
        "pack": pack, "stored_pack_hash": pack.snapshot_hash,
        "judges": judges, "validations": validations,
    }))
    report = build_report(uuid4(), verdict, pack, judges, validations, generated_at=NOW)
    # The retracted source remains in the auditable pack but is not shown as validated.
    assert verdict.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert pack.documents[0].integrity.status == "retracted"
    assert not report.key_evidence


def test_miri_like_production_failure_cannot_become_medical_contradiction() -> None:
    from app.verdict.models import AggregationMode

    request, context = case((C, C, None), mode=AggregationMode.PRODUCTION, miri=True)
    assert context.pack is not None
    verdict = VerdictService().aggregate(request, context)
    report = build_report(uuid4(), verdict, context.pack, context.judges,
                          context.validations, generated_at=NOW)
    output = format_report(report, uuid4())
    assert report.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert not report.production_qualified
    assert "DEVELOPMENT / EVALUATION ONLY" in output
    assert "isolation was not verified" in output
    assert "conflicts with this claim" not in output
    assert not report.key_evidence


def test_nonproduction_marker_is_schema_enforced() -> None:
    report, _, _ = report_for((S, S))
    payload = report.model_dump(mode="json")
    payload["verification_status"]["development_notice"] = None
    with pytest.raises(ValidationError, match="development notice"):
        LensReport.model_validate(payload)


def test_same_inputs_same_hash_timestamp_excluded_and_input_changes_detected() -> None:
    request, context = case((S, S))
    assert context.pack is not None
    verdict = VerdictService().aggregate(request, context)
    run_id = uuid4()
    first = build_report(run_id, verdict, context.pack, context.judges,
                         context.validations, generated_at=NOW)
    again = build_report(run_id, verdict, context.pack, context.judges,
                         context.validations, generated_at=NOW + timedelta(hours=1))
    assert first.semantic_hash == again.semantic_hash == semantic_report_hash(first)
    assert first.provenance.generated_at != again.provenance.generated_at
    assert build_report(uuid4(), verdict, context.pack, context.judges,
                        context.validations, generated_at=NOW).semantic_hash != (
                            first.semantic_hash
                        )
    passage = context.pack.passages[0]
    text = passage.passage.text + " Additional synthetic fixture sentence."
    altered_passage = passage.model_copy(update={
        "passage": passage.passage.model_copy(update={
            "text": text, "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        }),
    })
    changed_pack = build_evidence_pack(
        context.pack.claim_snapshot, context.pack.query_plan, context.pack.documents,
        (altered_passage, *context.pack.passages[1:]), retrieved_at=NOW,
    )
    assert changed_pack.snapshot_hash != context.pack.snapshot_hash
    changed_verdict = verdict.model_copy(update={
        "evidence_pack_hash": changed_pack.snapshot_hash, "semantic_hash": "0" * 64,
    })
    changed_verdict = changed_verdict.model_copy(update={
        "semantic_hash": semantic_result_hash(changed_verdict),
    })
    changed_judges = tuple(item.model_copy(update={
        "evidence_pack_hash": changed_pack.snapshot_hash,
    }) for item in context.judges)
    changed_validations = tuple(item.model_copy(update={
        "evidence_pack_hash": changed_pack.snapshot_hash,
    }) for item in context.validations)
    changed = build_report(run_id, changed_verdict, changed_pack, changed_judges,
                           changed_validations, generated_at=NOW)
    assert changed.semantic_hash != first.semantic_hash
    assert first.verdict == verdict.verdict == changed.verdict


def test_report_route_is_claim_scoped_and_gated() -> None:
    paths = set(create_app().openapi()["paths"])
    assert "/v1/analyses/{analysis_id}/claims/{claim_id}/report" in paths
    assert not any("verdict" in path for path in paths)
