"""Read-only, development-only export of explicitly named retained analyses.

Never starts the worker, runs cleanup, recovers deleted data, or calls a model.
Exports are sanitized developer artifacts under the ignored runtime directory.
"""

import argparse
import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.diagnostics import diagnostic_secrets, sanitize_diagnostic
from app.judging.config import configured_slots
from app.models.analysis_run import AnalysisRunRecord, ClaimAnalysisRunRecord
from app.models.claim import Claim
from app.models.judge_run import JudgeRunRecord
from app.models.judge_validation_run import JudgeValidationRunRecord
from app.models.report_run import ReportRunRecord
from app.models.retrieval import EvidencePackRecord, RetrievalQuery, RetrievalRun
from app.models.verdict_run import VerdictRunRecord
from app.validation.numeric import compare_statement_numbers, extract_quantities

DEFAULT_ANALYSES = (
    "75b56567-dd52-4e92-806d-ea2471bf6dc7",
    "1e58f2e8-f1cc-4e05-94af-1e008c22307d",
)


def record_json(record: object) -> dict[str, object]:
    mapper = inspect(type(record))
    assert mapper is not None
    return {column.key: getattr(record, column.key)
            for column in mapper.columns}


def quote_diagnostic(quote: str, source: str) -> dict[str, object]:
    if quote in source:
        return {"category": "exact", "first_divergence": None}
    def collapsed(text: str) -> str:
        return re.sub(r"\s+", " ", text)
    if collapsed(quote) in collapsed(source):
        category = "whitespace"
    elif "..." in quote or "…" in quote:
        category = "noncontiguous_quote"
    elif re.sub(r"\W", "", quote) in re.sub(r"\W", "", source):
        category = "punctuation"
    else:
        category = "substantive_or_wrong_reference"
    match = SequenceMatcher(None, quote, source).find_longest_match()
    source_start = max(0, match.b - match.a)
    aligned = source[source_start:]
    offset = next((i for i, (a, b) in enumerate(zip(quote, aligned, strict=False))
                   if a != b), min(len(quote), len(aligned)))
    return {"category": category, "first_divergence": offset,
            "source_start": source_start, "source_offset": source_start + offset,
            "proposed_quote": quote, "frozen_source": source}


def capture(session: Session, analysis_id: UUID) -> dict[str, object]:
    analysis = session.get(AnalysisRunRecord, analysis_id)
    if analysis is None:
        return {"analysis_id": str(analysis_id), "availability": "not_retained",
                "reconstruction": False}
    if analysis.purge_after <= datetime.now(UTC):
        return {"analysis_id": str(analysis_id), "availability": "expired_not_exported",
                "reconstruction": False}
    claims = list(session.scalars(select(ClaimAnalysisRunRecord).where(
        ClaimAnalysisRunRecord.analysis_run_id == analysis_id)))
    captured: list[dict[str, object]] = []
    ledger: list[dict[str, object]] = []
    for checkpoint in claims:
        pack = session.get(EvidencePackRecord, checkpoint.evidence_pack_id)
        claim = session.get(Claim, checkpoint.claim_id)
        judges = list(session.scalars(select(JudgeRunRecord).where(
            JudgeRunRecord.claim_id == checkpoint.claim_id).order_by(
                JudgeRunRecord.slot, JudgeRunRecord.semantic_revision_number)))
        validations = list(session.scalars(select(JudgeValidationRunRecord).where(
            JudgeValidationRunRecord.judge_run_id.in_([judge.id for judge in judges]))))
        raw_passages = cast(list[dict[str, Any]], pack.snapshot_json["passages"] if pack else [])
        passages = {item["evidence_id"]: item["passage"]["text"] for item in raw_passages}
        diagnostics: list[dict[str, object]] = []
        for judge in judges:
            decision = cast(dict[str, Any], judge.decision_json or {})
            for statement in decision.get("statements", []):
                refs = statement.get("evidence_refs", [])
                quotes = " ".join(ref["quote"] for ref in refs)
                numeric, asserted, source = compare_statement_numbers(statement["text"], quotes)
                diagnostics.append({
                    "judge_id": str(judge.id), "statement_id": statement["statement_id"],
                    "text": statement["text"], "numeric_status": numeric,
                    "asserted_quantities": [asdict(q) for q in
                                            extract_quantities(statement["text"])],
                    "source_quantities": [asdict(q) for q in extract_quantities(quotes)],
                    "mismatch_asserted": asdict(asserted) if asserted else None,
                    "mismatch_source": asdict(source) if source else None,
                    "quotes": [quote_diagnostic(ref["quote"], passages.get(ref["evidence_id"], ""))
                               | {"evidence_id": ref["evidence_id"]} for ref in refs],
                })
            for audit in (v for v in validations if v.judge_run_id == judge.id):
                for issue in cast(list[dict[str, Any]],
                                  audit.result_json.get("targeted_issues", [])):
                    failure = issue["issue_code"]
                    category = ("parser_uncertainty" if failure == "NUMERIC_UNCERTAIN" else
                                "semantic_disagreement" if failure in {
                                    "STATEMENT_ATTRIBUTION_FAILED", "CONCLUSION_NOT_JUSTIFIED"}
                                else "hard_defect")
                    ledger.append({"analysis_id": str(analysis_id), "judge_id": str(judge.id),
                                   "slot": judge.slot, "finding": issue["target_id"],
                                   "failure": failure, "category": category,
                                   "required_by_conclusion": issue["target_id"] == "conclusion"
                                   or issue["target_id"] in
                                   decision.get("conclusion", {}).get(
                                       "based_on_statement_ids", [])})
                if audit.error_category:
                    ledger.append({"analysis_id": str(analysis_id), "judge_id": str(judge.id),
                                   "slot": judge.slot, "failure": audit.error_category,
                                   "category": "provider_failure"})
            if judge.error_category:
                ledger.append({"analysis_id": str(analysis_id), "judge_id": str(judge.id),
                               "slot": judge.slot, "failure": judge.error_category,
                               "category": "contract_failure",
                               "raw_failed_response_retained": judge.response_json is not None})
        run = session.get(RetrievalRun, pack.run_id) if pack else None
        queries = list(session.scalars(select(RetrievalQuery).where(
            RetrievalQuery.run_id == pack.run_id))) if pack else []
        verdict = session.get(VerdictRunRecord, checkpoint.verdict_run_id)
        report = session.get(ReportRunRecord, checkpoint.report_run_id)
        captured.append({"checkpoint": record_json(checkpoint),
                         "claim": record_json(claim) if claim else None,
                         "pack": record_json(pack) if pack else None,
                         "retrieval": record_json(run) if run else None,
                         "queries": [record_json(q) for q in queries],
                         "judges": [record_json(j) for j in judges],
                         "validations": [record_json(v) for v in validations],
                         "diagnostics": diagnostics,
                         "verdict": record_json(verdict) if verdict else None,
                         "report": record_json(report) if report else None})
    return {"analysis_id": str(analysis_id), "availability": "retained_original",
            "captured_at": datetime.now(UTC), "purge_after": analysis.purge_after,
            "analysis": record_json(analysis), "claims": captured, "rejection_ledger": ledger,
            "limitations": ["Historical failed schema responses and semantic request bodies "
                            "were not persisted; expiring debug traces are not recoverable."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", action="append")
    parser.add_argument("--output", type=Path, default=Path("../runtime/reliability"))
    parser.add_argument("--database-url", help="Optional local connection; never exported")
    args = parser.parse_args()
    settings_args: dict[str, Any] = {"_env_file": Path("../.env")}
    settings = Settings(**settings_args)
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Replay export is development/test only.")
    runtime = Path(__file__).resolve().parents[3] / "runtime"
    if not args.output.resolve().is_relative_to(runtime):
        raise SystemExit("Replay output must stay inside the ignored runtime directory.")
    slots = configured_slots(settings)
    args.output.mkdir(parents=True, exist_ok=True)
    with Session(create_engine(args.database_url or settings.database_url,
                               connect_args={"connect_timeout": 5})) as session:
        for identifier in args.analysis or DEFAULT_ANALYSES:
            payload = capture(session, UUID(identifier))
            payload["effective_configuration"] = {
                "app_env": settings.app_env,
                "judges": [{"slot": s.slot, "provider": s.provider,
                            "model": s.model, "model_family": s.model_family} for s in slots],
            }
            # Do not overwrite an earlier capture; append a distinct local artifact.
            path = args.output / f"{identifier}-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.json"
            path.write_text(json.dumps(sanitize_diagnostic(payload, diagnostic_secrets(settings)),
                                       ensure_ascii=False, indent=2, default=str),
                            encoding="utf-8")
            print(f"{identifier} {payload['availability']} -> {path}")


if __name__ == "__main__":
    main()
