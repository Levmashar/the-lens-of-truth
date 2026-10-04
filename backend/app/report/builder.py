"""Pure, controlled prose and source cards from one frozen verdict audit."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from app.judging.models import JudgeDecisionV2, JudgeLabel, JudgeRun
from app.judging.prompt import input_snapshot_hash, prepare_judge_input
from app.report.explanation import build_explanation
from app.report.models import (
    EvidenceRole,
    EvidenceState,
    ExcludedAssessment,
    LensReport,
    NeutralRetrievedSource,
    ReportClaim,
    ReportJudgeSummary,
    ReportProvenance,
    ReportReason,
    ReportVerificationStatus,
    SourceCard,
    SourceExcerpt,
    SourceReference,
)
from app.retrieval.evidence_pack import canonical_pack_bytes
from app.retrieval.models import EvidencePack
from app.validation.models import (
    CitationValidation,
    ConclusionJustificationStatus,
    EntailmentStatus,
    IssueCode,
    JudgeValidationRun,
    RelationAlignment,
    StatementAttributionStatus,
    ValidationStatus,
)
from app.validation.numeric import extract_quantities
from app.verdict.models import AggregationMode, LensVerdict, ReasonCode, VerdictResult
from app.verdict.service import semantic_result_hash

REPORT_VERSION = "1.3"
BUILDER_VERSION = "report-builder-1.5"
MAX_EXCERPT_CHARS = 600
DEVELOPMENT_NOTICE = (
    "Development/evaluation result — production evidence-isolation or model "
    "qualification requirements were not satisfied. Do not use as a trusted medical report."
)
SAFETY_NOTICE = (
    "This report summarizes retrieved evidence, not personal diagnosis or treatment advice. "
    "For urgent symptoms or personal medical decisions, seek appropriate professional care."
)

DISPLAY_LABELS: dict[LensVerdict, str] = {
    LensVerdict.SUPPORTED: "Supported",
    LensVerdict.CONTRADICTED: "Contradicted",
    LensVerdict.NOT_ENOUGH_EVIDENCE: "Not Enough Evidence",
    LensVerdict.UNABLE_TO_VERIFY_RELIABLY: "Unable to Verify Reliably",
}

REASON_TEXT: dict[ReasonCode, str] = {
    ReasonCode.SUPPORTED_BY_MULTIPLE_VALIDATED_JUDGES:
        "Multiple independent assessments supported the claim and passed citation validation.",
    ReasonCode.CONTRADICTED_BY_MULTIPLE_VALIDATED_JUDGES:
        "Multiple independent assessments conflicted with the claim "
        "and passed citation validation.",
    ReasonCode.EVALUATION_SINGLE_VALIDATED_ASSESSMENT:
        "One assessment passed evidence-use validation. This development result is "
        "provisional and is not a production medical conclusion.",
    ReasonCode.CAUSAL_EVIDENCE_TOO_INDIRECT:
        "The cited study designs do not directly establish or rule out the claimed effect.",
    ReasonCode.UNANIMOUS_HIGH_RISK_SUPPORT:
        "All required validated assessments supported this high-risk claim.",
    ReasonCode.UNANIMOUS_HIGH_RISK_CONTRADICTION:
        "All required validated assessments conflicted with this high-risk claim.",
    ReasonCode.VALIDATED_JUDGE_DISAGREEMENT:
        "Validated assessments disagreed about how the evidence should be interpreted.",
    ReasonCode.INSUFFICIENT_DECISIVE_EVIDENCE:
        "The available evidence did not justify a decisive conclusion.",
    ReasonCode.ALL_JUDGES_NOT_ENOUGH_EVIDENCE:
        "All qualified assessments found the evidence insufficient for a decisive conclusion.",
    ReasonCode.RETRIEVAL_NO_RESULTS:
        "The configured source search completed but returned no evidence for this claim.",
    ReasonCode.RETRIEVAL_TECHNICAL_FAILURE:
        "Evidence retrieval could not be completed reliably.",
    ReasonCode.PACK_HASH_MISMATCH: "Evidence provenance could not be verified.",
    ReasonCode.PACK_UNAVAILABLE: "The frozen evidence snapshot was unavailable.",
    ReasonCode.PACK_VERSION_UNSUPPORTED:
        "The frozen evidence snapshot version was unsupported.",
    ReasonCode.PACK_SELECTION_INVALID:
        "The frozen evidence selection did not pass integrity checks.",
    ReasonCode.CLAIM_UNAVAILABLE: "The submitted claim was unavailable for verification.",
    ReasonCode.NORMALIZATION_INCOMPLETE:
        "Medical claim normalization was incomplete.",
    ReasonCode.RISK_CLASS_INVALID: "The claim's safety classification was unavailable.",
    ReasonCode.AUDIT_RECORD_MISSING: "A required assessment audit record was missing.",
    ReasonCode.AUDIT_RECORD_MISMATCH: "Assessment audit records did not match the evidence.",
    ReasonCode.AUDIT_RECORD_INVALID: "Assessment audit records could not be validated.",
    ReasonCode.INSUFFICIENT_QUALIFIED_JUDGES:
        "Too few qualified assessments were available for a reliable conclusion.",
    ReasonCode.INSUFFICIENT_VALIDATED_JUDGES:
        "Too few assessments passed evidence-use validation.",
    ReasonCode.SEARCH_ISOLATION_UNVERIFIED:
        "Model evidence isolation was not verified for this run.",
    ReasonCode.SEARCH_GUARD_BYPASSED:
        "A development-only search safety guard was bypassed.",
    ReasonCode.MODEL_IDENTITY_UNVERIFIED:
        "The underlying model identity was not verified.",
    ReasonCode.MODEL_FAMILY_UNVERIFIED:
        "Independent model-family identity was not verified.",
    ReasonCode.DUPLICATE_MODEL_FAMILY:
        "Assessments could not be confirmed as independent model families.",
    ReasonCode.DUPLICATE_JUDGE_SLOT: "Assessment slots were duplicated.",
    ReasonCode.JUDGE_FAILED: "An evidence assessment did not complete successfully.",
    ReasonCode.VALIDATION_UNAVAILABLE:
        "Citation validation was unavailable for an assessment.",
    ReasonCode.VALIDATION_PROVIDER_UNAPPROVED:
        "The citation-validation source was not approved for production.",
    ReasonCode.VALIDATION_PARTIAL:
        "An assessment's evidence use was only partially validated.",
    ReasonCode.VALIDATION_INVALID:
        "An assessment's evidence use did not pass validation.",
    ReasonCode.VALIDATION_FATAL_ISSUE:
        "A material citation or evidence-use problem excluded an assessment.",
    ReasonCode.EVALUATION_ONLY:
        "This run is for development or evaluation, not a production medical result.",
}
assert set(REASON_TEXT) == set(ReasonCode)


def semantic_report_hash(report: LensReport) -> str:
    """Exclude only the generated timestamp and this digest from the report hash."""

    semantic = report.model_dump(mode="json", exclude={
        "semantic_hash": True, "provenance": {"generated_at": True},
    })
    if report.report_version not in {"1.2", "1.3"}:
        for card in semantic["key_evidence"]:
            for field in ("document_id", "source_kind", "organization", "document_purpose",
                          "analysis_design", "exposure_assignment", "attribution", "currency",
                          "excerpts"):
                card.pop(field, None)
    return hashlib.sha256(json.dumps(
        semantic, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _summary(
    verdict: LensVerdict, reasons: tuple[ReasonCode, ...], *, selected_evidence_count: int,
) -> str:
    if ReasonCode.EVALUATION_SINGLE_VALIDATED_ASSESSMENT in reasons:
        relation = "supports" if verdict == LensVerdict.SUPPORTED else "conflicts with"
        return ("One validated assessment " + relation + " this claim. "
                "This is a provisional development result, not a trusted medical report.")
    if verdict == LensVerdict.SUPPORTED:
        return "The available validated evidence supports this claim at the stated scope."
    if verdict == LensVerdict.CONTRADICTED:
        return "The available validated evidence conflicts with this claim at the stated scope."
    if verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY:
        return "The system could not complete a sufficiently reliable verification."
    if ReasonCode.RETRIEVAL_NO_RESULTS in reasons:
        return "The source search completed without results; no medical conclusion was reached."
    if not selected_evidence_count and ReasonCode.INSUFFICIENT_DECISIVE_EVIDENCE in reasons:
        return ("Retrieved sources did not qualify for this claim's evidence review; "
                "no medical conclusion was reached.")
    if ReasonCode.CAUSAL_EVIDENCE_TOO_INDIRECT in reasons:
        return ("The cited evidence is too indirect to establish or rule out "
                "this causal claim.")
    if ReasonCode.VALIDATED_JUDGE_DISAGREEMENT in reasons:
        return "Validated assessments disagreed; no decisive conclusion was justified."
    return "Relevant evidence did not justify a reliable supported or contradicted conclusion."


def _evidence_state(verdict: LensVerdict, reasons: tuple[ReasonCode, ...]) -> EvidenceState:
    if verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY:
        return EvidenceState.VERIFICATION_INCOMPLETE
    if verdict == LensVerdict.SUPPORTED:
        return EvidenceState.VALIDATED_SUPPORT
    if verdict == LensVerdict.CONTRADICTED:
        return EvidenceState.VALIDATED_CONTRADICTION
    if ReasonCode.RETRIEVAL_NO_RESULTS in reasons:
        return EvidenceState.NO_RESULTS
    if ReasonCode.VALIDATED_JUDGE_DISAGREEMENT in reasons:
        return EvidenceState.CONFLICTING
    return EvidenceState.RELEVANT_BUT_INSUFFICIENT


def _assessment_description(counts: dict[JudgeLabel, int]) -> str:
    names = {
        JudgeLabel.SUPPORTED: "supported the claim",
        JudgeLabel.CONTRADICTED: "contradicted the claim",
        JudgeLabel.NOT_ENOUGH_EVIDENCE: "found the evidence insufficient",
    }
    parts = [f"{counts[label]} qualified assessment(s) {names[label]}"
             for label in JudgeLabel if counts.get(label, 0)]
    return "; ".join(parts) + "." if parts else "No qualified assessments were available."


def _limitations(
    pack: EvidencePack, validations: tuple[JudgeValidationRun, ...],
) -> tuple[str, ...]:
    issues = {issue for run in validations for issue in (
        *run.result.fatal_issue_codes, *run.result.warnings,
        *(code for citation in (*run.result.citation_validations,
                                  *run.result.opposing_citation_validations)
          for code in (*citation.issue_codes, *citation.warnings)),
    )}
    citations = (citation for run in validations for citation in (
        *run.result.citation_validations, *run.result.opposing_citation_validations,
    ))
    weaker_relation = any(citation.relation_alignment == RelationAlignment.WEAKER_THAN_CLAIM
                          for citation in citations)
    result: list[str] = []
    if IssueCode.MATERIAL_NUMERIC_MISMATCH in issues:
        if extract_quantities(pack.claim_snapshot.standalone_text):
            result.append("A claim number or an assessment's numeric use did not match its "
                          "cited source; the affected assessment was excluded.")
        else:
            result.append("An assessment misstated or could not verify a source number; "
                          "this is not a numerical error in the submitted claim.")
    if any(issue.issue_code == IssueCode.STATEMENT_NUMERIC_MISMATCH
           and issue.target_type == "judge_statement"
           for run in validations for issue in run.result.targeted_issues):
        result.append("A judge-introduced statistic did not match its own cited quotation; "
                      "the affected assessment was excluded.")
    if (IssueCode.RELATION_STRENGTH_MISMATCH in issues or weaker_relation) and (
        pack.claim_snapshot.claim_type == "causal"
    ):
        result.append("Association does not by itself establish causation at the claim's "
                      "stated causal scope.")
    if IssueCode.MATERIAL_SCOPE_MISMATCH in issues:
        result.append("At least one assessment used evidence with a materially different "
                      "population, intervention, comparator, outcome, or timeframe.")
    elif IssueCode.PARTIAL_SCOPE_MATCH in issues:
        result.append("Some evidence only partially matched the claim's stated scope.")
    if IssueCode.RETRACTED_CITATION in issues:
        result.append("A cited source was retracted and excluded from validated evidence.")
    if IssueCode.INTEGRITY_UNKNOWN in issues or IssueCode.EXPRESSION_OF_CONCERN in issues:
        result.append("At least one source has an integrity limitation noted in validation.")
    return tuple(result)


def _role(label: JudgeLabel, citation_role: str) -> EvidenceRole:
    if label == JudgeLabel.NOT_ENOUGH_EVIDENCE:
        return EvidenceRole.RELEVANT_BUT_INSUFFICIENT
    supporting = (label == JudgeLabel.SUPPORTED) == (citation_role == "cited")
    return EvidenceRole.SUPPORTING if supporting else EvidenceRole.OPPOSING


def _eligible_citation(citation: CitationValidation) -> bool:
    return (citation.exists and citation.selected_for_judging
            and citation.passage_hash_matches and citation.document_provenance_exists
            and citation.integrity_status != "retracted" and not citation.issue_codes
            and citation.entailment_status == EntailmentStatus.ENTAILS_JUDGE_USE)


def _cards(
    verdict: VerdictResult, pack: EvidencePack, judges: tuple[JudgeRun, ...],
    validations: tuple[JudgeValidationRun, ...],
) -> tuple[SourceCard, ...]:
    # Operational inability must never look like a medical evidence conclusion.
    if verdict.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY:
        return ()
    by_judge = {item.judge_run_id: item for item in judges}
    by_validation = {item.judge_run_id: item for item in validations}
    passages = {item.evidence_id: item for item in pack.passages}
    documents = {item.document_id: item for item in pack.documents}
    uses: dict[str, list[tuple[EvidenceRole, UUID, UUID]]] = {}
    for qualification in verdict.judge_qualifications:
        if not qualification.qualified:
            continue
        judge = by_judge[qualification.judge_run_id]
        validation = by_validation.get(judge.judge_run_id)
        if judge.decision is None or validation is None:
            continue
        limited_inconclusive = (
            verdict.mode == AggregationMode.FIXTURE_OR_EVALUATION
            and verdict.verdict == LensVerdict.NOT_ENOUGH_EVIDENCE
            and judge.decision.label == JudgeLabel.NOT_ENOUGH_EVIDENCE
            and validation.status == ValidationStatus.PARTIALLY_VALIDATED
            and IssueCode.PARTIAL_SCOPE_MATCH in validation.result.warnings
        )
        if validation.status != ValidationStatus.VALIDATED and not limited_inconclusive:
            continue
        if isinstance(judge.decision, JudgeDecisionV2):
            conclusion = validation.result.conclusion_justification
            if (conclusion is None or conclusion.status != ConclusionJustificationStatus.JUSTIFIED
                    or judge.input_snapshot_hash is None
                    or judge.input_snapshot_json is None):
                continue
            prepared = prepare_judge_input(
                judge.evidence_pack_id, pack,
                version=judge.input_snapshot_version or "judge-input-2.0",
            )
            if (judge.input_snapshot_hash != prepared.input_snapshot_hash
                    or input_snapshot_hash(judge.input_snapshot_json)
                    != prepared.input_snapshot_hash):
                raise ValueError("Judge-visible input snapshot is invalid")
            attributed = {item.statement_id: item
                          for item in validation.result.statement_attributions}
            for statement in judge.decision.statements:
                if statement.statement_id not in conclusion.based_on_statement_ids:
                    continue
                item = attributed.get(statement.statement_id)
                if item is None or item.status != StatementAttributionStatus.SUPPORTED_BY_SOURCES:
                    continue
                for ref in statement.evidence_refs:
                    if ref.evidence_id not in prepared.selected_ids:
                        raise ValueError("Validated statement cited nonvisible evidence")
                    role = _role(judge.decision.label, "cited")
                    uses.setdefault(ref.evidence_id, []).append(
                        (role, judge.judge_run_id, validation.id)
                    )
            continue
        for citation in (*validation.result.citation_validations,
                         *validation.result.opposing_citation_validations):
            if not _eligible_citation(citation):
                continue
            if citation.evidence_id not in pack.selected_evidence_ids:
                raise ValueError("Qualified citation is outside selected frozen evidence")
            if citation.evidence_id not in passages:
                raise ValueError("Qualified citation is outside the frozen Evidence Pack")
            role = _role(judge.decision.label, citation.role)
            uses.setdefault(citation.evidence_id, []).append(
                (role, judge.judge_run_id, validation.id)
            )
    cards: list[SourceCard] = []
    display_ids = tuple(dict.fromkeys((*pack.selected_evidence_ids, *uses)))
    for evidence_id in display_ids:
        if evidence_id not in uses:
            continue
        passage = passages[evidence_id]
        document = documents.get(passage.passage.document_id)
        if document is None or document.integrity.status == "retracted":
            raise ValueError("Qualified evidence lacks safe frozen document provenance")
        if any(
            citation.integrity_status != document.integrity.status
            for validation in validations
            for citation in (*validation.result.citation_validations,
                             *validation.result.opposing_citation_validations)
            if (citation.evidence_id == evidence_id
                and validation.judge_run_id in {use[1] for use in uses[evidence_id]})
        ):
            raise ValueError("Qualified citation integrity differs from frozen source")
        if not document.canonical_url or not (document.pmid or document.authoritative):
            raise ValueError("Qualified evidence lacks source reference")
        text = passage.passage.text
        cards.append(SourceCard(
            evidence_id=evidence_id, pmid=document.pmid or None, doi=document.doi,
            title=document.title, journal=document.journal,
            publication_date=(document.publication_date.isoformat()
                              if document.publication_date else None),
            study_design=document.study_design, integrity_status=document.integrity.status,
            evidence_roles=tuple(dict.fromkeys(use[0] for use in uses[evidence_id])),
            exact_excerpt=text[:MAX_EXCERPT_CHARS],
            excerpt_truncated=len(text) > MAX_EXCERPT_CHARS,
            passage_sha256=passage.passage.content_sha256,
            passage_section=passage.passage.section, source_url=document.canonical_url,
            citation_validated=True,
            cited_by_judge_run_ids=tuple(dict.fromkeys(use[1] for use in uses[evidence_id])),
            cited_by_validation_run_ids=tuple(dict.fromkeys(use[2] for use in uses[evidence_id])),
            document_id=document.document_id, source_kind=document.source_kind,
            organization=document.authoritative.organization if document.authoritative else None,
            document_purpose=document.authoritative.document_purpose
            if document.authoritative else None,
            analysis_design=document.relationship_analysis.analysis_design
            if document.relationship_analysis else None,
            exposure_assignment=document.relationship_analysis.exposure_assignment
            if document.relationship_analysis else None,
            attribution=document.authoritative.attribution if document.authoritative else None,
            currency=document.authoritative.currency if document.authoritative else None,
            excerpts=(SourceExcerpt(evidence_id=evidence_id, source_unit_id=f"{evidence_id}.U1",
                                    section=passage.passage.section,
                                    exact_text=text,
                                    truncated=False,
                                    passage_sha256=passage.passage.content_sha256),),
        ))
    grouped: dict[str, SourceCard] = {}
    for card in cards:
        key = card.document_id or card.evidence_id
        previous = grouped.get(key)
        if previous:
            grouped[key] = previous.model_copy(update={
                "excerpts": (*previous.excerpts, *card.excerpts),
                "evidence_roles": tuple(dict.fromkeys((*previous.evidence_roles,
                                                       *card.evidence_roles))),
                "cited_by_judge_run_ids": tuple(dict.fromkeys((*previous.cited_by_judge_run_ids,
                                                               *card.cited_by_judge_run_ids))),
                "cited_by_validation_run_ids": tuple(dict.fromkeys((
                    *previous.cited_by_validation_run_ids, *card.cited_by_validation_run_ids))),
            })
        else:
            grouped[key] = card
    return tuple(grouped.values())


def _neutral_sources(
    verdict: VerdictResult, pack: EvidencePack,
) -> tuple[NeutralRetrievedSource, ...]:
    if (verdict.mode != AggregationMode.FIXTURE_OR_EVALUATION
            or verdict.verdict != LensVerdict.UNABLE_TO_VERIFY_RELIABLY):
        return ()
    passages = {item.evidence_id: item for item in pack.passages}
    documents = {item.document_id: item for item in pack.documents}
    cards: list[NeutralRetrievedSource] = []
    for evidence_id in pack.selected_evidence_ids[:5]:
        item = passages.get(evidence_id)
        document = documents.get(item.passage.document_id) if item else None
        if (item is None or document is None or document.integrity.status == "retracted"
                or not (document.pmid or document.authoritative) or not document.canonical_url):
            continue
        text = item.passage.text
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != item.passage.content_sha256:
            raise ValueError("Frozen neutral source passage hash is invalid")
        cards.append(NeutralRetrievedSource(
            evidence_id=evidence_id, pmid=document.pmid or None, doi=document.doi,
            title=document.title,
            publication_date=(document.publication_date.isoformat()
                              if document.publication_date else None),
            passage_section=item.passage.section,
            exact_excerpt=text[:MAX_EXCERPT_CHARS],
            excerpt_truncated=len(text) > MAX_EXCERPT_CHARS,
            passage_sha256=item.passage.content_sha256,
            source_url=document.canonical_url,
        ))
    return tuple(cards)


def build_report(
    verdict_run_id: UUID, verdict: VerdictResult, pack: EvidencePack,
    judges: tuple[JudgeRun, ...], validations: tuple[JudgeValidationRun, ...],
    *, generated_at: datetime | None = None,
) -> LensReport:
    """Present the existing verdict without recomputing it or fetching outside data."""

    if verdict.semantic_hash != semantic_result_hash(verdict):
        raise ValueError("Verdict semantic hash mismatch")
    actual_pack_hash = hashlib.sha256(canonical_pack_bytes(
        pack.claim_snapshot, pack.query_plan, pack.documents, pack.passages,
        pack.selected_evidence_ids, pack_version=pack.evidence_pack_version,
    )).hexdigest()
    if (pack.evidence_pack_version not in {"1.3", "1.4", "1.5"}
            or pack.snapshot_hash != actual_pack_hash
            or verdict.evidence_pack_hash != actual_pack_hash
            or verdict.claim_id != pack.claim_id
            or verdict.claim_id != pack.claim_snapshot.claim_id):
        raise ValueError("Frozen Evidence Pack provenance mismatch")
    if ({item.judge_run_id for item in judges} != set(verdict.input_judge_run_ids)
            or {item.id for item in validations} != set(verdict.input_validation_run_ids)):
        raise ValueError("Explicit judge/validation audit IDs are incomplete")
    if len(judges) != len(verdict.input_judge_run_ids) or len(validations) != len(
        verdict.input_validation_run_ids
    ):
        raise ValueError("Duplicate audit IDs")
    if (any(item.evidence_pack_id != verdict.evidence_pack_id
            or item.evidence_pack_hash != actual_pack_hash for item in judges)
            or any(item.evidence_pack_id != verdict.evidence_pack_id
                   or item.evidence_pack_hash != actual_pack_hash for item in validations)):
        raise ValueError("Audit row belongs to a different Evidence Pack")
    if any(item.judge_run_id not in verdict.input_judge_run_ids for item in validations):
        raise ValueError("Validation references an unlisted judge")
    if {item.judge_run_id for item in verdict.judge_qualifications} - set(
        verdict.input_judge_run_ids
    ):
        raise ValueError("Verdict qualification references an unlisted judge")
    cards = _cards(verdict, pack, judges, validations)
    explanation = build_explanation(verdict, pack, judges, validations, cards)
    if verdict.verdict in {LensVerdict.SUPPORTED, LensVerdict.CONTRADICTED} and not cards:
        raise ValueError("Decisive verdict has no validated frozen citation to present")
    reasons = tuple(ReportReason(code=code, text=REASON_TEXT[code])
                    for code in verdict.reason_codes)
    excluded = tuple(ExcludedAssessment(
        judge_run_id=item.judge_run_id, slot=item.slot,
        reasons=tuple(ReportReason(code=code, text=REASON_TEXT[code])
                      for code in item.exclusion_reasons),
    ) for item in verdict.judge_qualifications if not item.qualified)
    provenance = ReportProvenance(
        report_version=REPORT_VERSION, verdict_run_id=verdict_run_id,
        verdict_policy_version=verdict.policy_version,
        verdict_semantic_hash=verdict.semantic_hash,
        evidence_pack_id=verdict.evidence_pack_id,
        evidence_pack_hash=verdict.evidence_pack_hash,
        evidence_pack_version=pack.evidence_pack_version,
        judge_run_ids=verdict.input_judge_run_ids,
        judge_validation_run_ids=verdict.input_validation_run_ids,
        report_builder_version=BUILDER_VERSION,
        generated_at=generated_at or datetime.now(UTC),
        production_qualified=verdict.production_qualified,
    )
    display_label = DISPLAY_LABELS[verdict.verdict]
    if ReasonCode.EVALUATION_SINGLE_VALIDATED_ASSESSMENT in verdict.reason_codes:
        display_label = f"Provisional {display_label} (Development Only)"
    result = LensReport(
        report_version=REPORT_VERSION, verdict_run_id=verdict_run_id,
        claim=ReportClaim(text=pack.claim_snapshot.standalone_text,
                          claim_type=pack.claim_snapshot.claim_type),
        verdict=verdict.verdict, verdict_display=display_label,
        headline=display_label,
        short_summary=explanation.summary, verdict_explanation=explanation,
        why_this_result=reasons, key_evidence=cards,
        neutral_retrieved_sources=_neutral_sources(verdict, pack),
        evidence_limitations=_limitations(pack, validations),
        judge_summary=ReportJudgeSummary(
            qualified=verdict.qualified_judges, excluded=verdict.excluded_judges,
            validated_label_counts=verdict.validated_label_counts,
            description=_assessment_description(verdict.validated_label_counts),
            excluded_assessments=excluded,
        ),
        verification_status=ReportVerificationStatus(
            evidence_state=_evidence_state(verdict.verdict, verdict.reason_codes),
            validated_citations_shown=len(cards),
            production_qualified=verdict.production_qualified,
            development_notice=(None if verdict.production_qualified else DEVELOPMENT_NOTICE),
        ),
        sources=tuple(SourceReference(evidence_id=card.evidence_id, pmid=card.pmid,
                                      doi=card.doi, url=card.source_url)
                      for card in cards),
        safety_notice=SAFETY_NOTICE,
        production_qualified=verdict.production_qualified,
        provenance=provenance, semantic_hash="0" * 64,
    )
    return result.model_copy(update={"semantic_hash": semantic_report_hash(result)})
