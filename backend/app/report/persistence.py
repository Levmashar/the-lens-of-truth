"""Load a named verdict and its recorded audit rows, then append a report snapshot."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.report_run import ReportRunRecord
from app.models.verdict_run import VerdictRunRecord
from app.report.builder import BUILDER_VERSION, build_report, semantic_report_hash
from app.report.models import LensReport
from app.verdict.models import AggregationInput, VerdictResult
from app.verdict.persistence import load_aggregation_context
from app.verdict.service import semantic_result_hash


def build_report_for_verdict(session: Session, verdict_run_id: UUID) -> LensReport:
    """Never select a latest run or redo aggregation; verify exact persisted inputs."""

    row = session.get(VerdictRunRecord, verdict_run_id)
    if row is None:
        raise ValueError("Verdict run not found")
    result = VerdictResult.model_validate(row.result_json)
    if (row.semantic_hash != result.semantic_hash
            or result.semantic_hash != semantic_result_hash(result)
            or row.claim_id != result.claim_id
            or row.evidence_pack_id != result.evidence_pack_id
            or row.evidence_pack_hash != result.evidence_pack_hash
            or row.policy_version != result.policy_version
            or row.mode != result.mode.value
            or row.verdict != result.verdict.value
            or row.reason_codes != [code.value for code in result.reason_codes]
            or row.production_qualified != result.production_qualified
            or row.judge_run_ids != [str(item) for item in result.input_judge_run_ids]
            or row.judge_validation_run_ids != [str(item)
                                                 for item in result.input_validation_run_ids]):
        raise ValueError("Verdict audit row disagrees with its immutable result")
    request = AggregationInput(
        claim_id=result.claim_id, evidence_pack_id=result.evidence_pack_id,
        evidence_pack_hash=result.evidence_pack_hash,
        judge_run_ids=result.input_judge_run_ids,
        judge_validation_run_ids=result.input_validation_run_ids,
        mode=result.mode, policy_version=result.policy_version,
    )
    context = load_aggregation_context(session, request)
    if context.pack is None or not context.audit_records_valid:
        raise ValueError("Frozen Evidence Pack or audit records are unavailable")
    if (context.stored_pack_hash != result.evidence_pack_hash
            or context.stored_pack_version != context.pack.evidence_pack_version
            or context.stored_pack_claim_id != result.claim_id):
        raise ValueError("Stored Evidence Pack provenance mismatch")
    return build_report(
        verdict_run_id, result, context.pack, context.judges, context.validations,
    )


def persist_report_run(session: Session, report: LensReport) -> ReportRunRecord:
    """Each execution inserts a new row; the database rejects subsequent UPDATEs."""

    verdict_row = session.get(VerdictRunRecord, report.verdict_run_id)
    if verdict_row is None or verdict_row.semantic_hash != report.provenance.verdict_semantic_hash:
        raise ValueError("Report does not match a stored VerdictRun")
    if (report.semantic_hash != semantic_report_hash(report)
            or report.report_version != report.provenance.report_version
            or report.provenance.report_builder_version != BUILDER_VERSION
            or report.production_qualified != verdict_row.production_qualified):
        raise ValueError("Report provenance or semantic hash mismatch")
    record = ReportRunRecord(
        verdict_run_id=report.verdict_run_id,
        report_version=report.report_version,
        report_builder_version=BUILDER_VERSION,
        result_json=report.model_dump(mode="json"),
        semantic_hash=report.semantic_hash,
        production_qualified=report.production_qualified,
    )
    try:
        session.add(record)
        session.commit()
        session.refresh(record)
        return record
    except Exception:
        session.rollback()
        raise
