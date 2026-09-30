"""Developer-only human-readable report from a named, persisted verdict run."""

import argparse
from uuid import UUID

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.report.models import LensReport
from app.report.persistence import build_report_for_verdict, persist_report_run


def format_report(report: LensReport, audit_id: UUID) -> str:
    """Keep source excerpts visibly separate from Lens-generated interpretation."""

    lines: list[str] = []
    if report.verification_status.development_notice:
        lines.extend(["DEVELOPMENT / EVALUATION ONLY",
                      report.verification_status.development_notice, ""])
    lines.extend([
        "CLAIM (SUBMITTED; NOT AN ENDORSEMENT)", report.claim.text,
        "", "RESULT", report.verdict_display,
        "", "SUMMARY (LENS PRESENTATION)", report.short_summary,
        "", "WHY", *(f"- {item.text} [{item.code.value}]"
                      for item in report.why_this_result),
        "", "KEY EVIDENCE (EXACT FROZEN EXCERPTS)",
    ])
    if not report.key_evidence:
        lines.append("No validated evidence cards are shown for this result.")
    for card in report.key_evidence:
        lines.extend([
            "", card.evidence_id, f"Title: {card.title}",
            f"Study design (metadata): {card.study_design}",
            f"PMID: {card.pmid}", f"DOI: {card.doi or 'none'}",
            f"Role: {', '.join(role.value for role in card.evidence_roles)}",
            f"Validated citation: {'yes' if card.citation_validated else 'no'}",
            f"Source: {card.source_url}", "Excerpt (source text):", card.exact_excerpt,
        ])
    if report.neutral_retrieved_sources:
        lines.append("\nRETRIEVED SOURCES — NOT VALIDATED SUPPORT FOR A FINAL CONCLUSION")
        for source in report.neutral_retrieved_sources:
            lines.extend([source.evidence_id, f"PMID: {source.pmid}",
                          f"Title: {source.title}", source.exact_excerpt])
    lines.extend(["", "LIMITATIONS", *([f"- {item}" for item in report.evidence_limitations]
                                         or ["- No additional material limitation recorded."]),
                  "", "ASSESSMENTS", report.judge_summary.description,
                  f"Qualified: {report.judge_summary.qualified}",
                  f"Excluded: {report.judge_summary.excluded}"])
    for item in report.judge_summary.excluded_assessments:
        lines.append(f"- Excluded slot {item.slot}: "
                     + "; ".join(reason.text for reason in item.reasons))
    lines.extend([
        "", "PROVENANCE", f"Verdict run: {report.verdict_run_id}",
        f"Evidence Pack: {report.provenance.evidence_pack_id}",
        f"Pack hash: {report.provenance.evidence_pack_hash}",
        f"Policy: {report.provenance.verdict_policy_version}",
        f"Report version: {report.report_version}",
        f"Report semantic hash: {report.semantic_hash}",
        f"Report audit ID: {audit_id}", "", "SAFETY", report.safety_notice,
        "", f"PRODUCTION QUALIFIED: {str(report.production_qualified).lower()}",
    ])
    return "\n".join(lines)


def smoke(verdict_run_id: UUID) -> None:
    if get_settings().app_env not in {"development", "test"}:
        raise SystemExit("The report smoke command is development/test only.")
    with SessionLocal() as session:
        report = build_report_for_verdict(session, verdict_run_id)
        record = persist_report_run(session, report)
    print(format_report(report, record.id))


def main() -> None:
    parser = argparse.ArgumentParser(description="Report a named, stored verdict run")
    parser.add_argument("verdict_run_id", type=UUID)
    args = parser.parse_args()
    smoke(args.verdict_run_id)


if __name__ == "__main__":
    main()
