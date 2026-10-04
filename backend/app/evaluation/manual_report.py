"""Read-only development export of one retained analysis; no model or retrieval calls."""

import argparse
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.routes.analyses import _debug_claim_diagnostics, _debug_judge_runs
from app.core.config import Settings
from app.models.analysis_run import AnalysisRunRecord, ClaimAnalysisRunRecord
from app.models.claim import Claim
from app.models.judge_validation_run import JudgeValidationRunRecord
from app.models.retrieval import EvidencePackRecord
from app.models.verdict_run import VerdictRunRecord
from app.retrieval.models import EvidencePack


def export_analysis(session: Session, analysis_id: UUID) -> dict[str, object]:
    run = session.get(AnalysisRunRecord, analysis_id)
    if run is None or run.purge_after <= datetime.now(UTC):
        raise ValueError("Analysis not found or expired")
    rows = session.scalars(select(ClaimAnalysisRunRecord).where(
        ClaimAnalysisRunRecord.analysis_run_id == analysis_id,
    ).order_by(ClaimAnalysisRunRecord.ordinal)).all()
    claims: list[dict[str, object]] = []
    for row in rows:
        claim = session.get(Claim, row.claim_id)
        if claim is None:
            continue
        verdict = session.get(VerdictRunRecord, row.verdict_run_id) if row.verdict_run_id else None
        pack_row = (session.get(EvidencePackRecord, row.evidence_pack_id)
                    if row.evidence_pack_id else None)
        pack = EvidencePack.model_validate(pack_row.snapshot_json) if pack_row else None
        selected = set(pack.selected_evidence_ids) if pack else set()
        selected_doc_ids = ({p.passage.document_id for p in pack.passages
                             if p.evidence_id in selected} if pack else set())
        judges = _debug_judge_runs(session, row)
        validator_attempts = 0
        for judge in judges:
            if judge.validation_run_id is not None:
                validation = session.get(JudgeValidationRunRecord, judge.validation_run_id)
                if validation is not None:
                    validator_attempts += validation.attempt_count
        claims.append({
            "claim_id": str(claim.id), "raw_claim": claim.raw_text,
            "normalized_claim": claim.normalized_text,
            "pico": claim.pico_json, "normalization_status": claim.normalization_status,
            "normalization_quality": claim.normalization_quality,
            "evidence_pack_id": str(pack_row.id) if pack_row else None,
            "evidence_pack_hash": pack_row.snapshot_hash if pack_row else None,
            "selected_sources": ([{"document_id": d.document_id, "source_kind": d.source_kind,
                                   "pmid": d.pmid or None, "title": d.title,
                                   "doi": d.doi, "role": d.evidence_role_hint}
                                  for d in pack.documents if d.document_id in selected_doc_ids]
                                 if pack else []),
            "judges": [j.model_dump(mode="json") for j in judges],
            "diagnostics": _debug_claim_diagnostics(session, row, verdict, []),
            "result": verdict.verdict if verdict else None,
            "audited_judge_attempts": sum(j.attempt_count for j in judges),
            "audited_validator_attempts": validator_attempts,
            "model_call_count_note": "Exact total unavailable outside the live debug trace.",
        })
    return {"analysis_id": str(analysis_id), "status": run.status,
            "purge_after": run.purge_after.isoformat(), "claims": claims,
            "retention_note": "Read only; export does not extend source retention."}


def _markdown(data: dict[str, object]) -> str:
    lines = [f"# Analysis {data['analysis_id']}", "", f"Status: {data['status']}", ""]
    items = data["claims"]
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        lines.extend([f"## Claim {item['claim_id']}", "", f"Claim: {item['raw_claim']}",
                      f"Normalized: {item['normalized_claim']}", f"Result: {item['result']}",
                      "", "```json", json.dumps(item, ensure_ascii=False, indent=2,
                                             default=str), "```", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", required=True, type=UUID)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    settings = Settings(_env_file="../.env")  # type: ignore[call-arg]
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Development/test only")
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        try:
            data = export_analysis(session, args.analysis)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    print(_markdown(data) if args.format == "markdown"
          else json.dumps(data, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
