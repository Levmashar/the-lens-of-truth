"""Developer-only offline validation of one persisted successful judge run."""

import argparse
import asyncio
import json
from uuid import UUID

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.judging.models import JudgeDecision, JudgeRun
from app.models.judge_run import JudgeRunRecord
from app.models.retrieval import EvidencePackRecord
from app.retrieval.models import EvidencePack
from app.validation.persistence import persist_validation_run
from app.validation.service import ValidationService


def _read_judge(row: JudgeRunRecord) -> JudgeRun:
    if row.outcome_status != "succeeded" or row.decision_json is None:
        raise ValueError("Only successful judge runs can be validated")
    return JudgeRun(
        judge_run_id=row.id, claim_id=row.claim_id,
        evidence_pack_id=row.evidence_pack_id, evidence_pack_hash=row.evidence_pack_hash,
        slot=row.slot, provider=row.provider, model=row.model,
        model_family=row.model_family, model_snapshot=row.model_snapshot,
        schema_version_inferred=row.schema_version_inferred,
        model_identity_verified=row.model_identity_verified,
        model_family_verified=row.model_family_verified,
        search_override_active=row.search_override_active,
        search_guard_bypassed=row.search_guard_bypassed,
        search_isolation_verified=row.search_isolation_verified,
        prompt_version=row.prompt_version, prompt_hash=row.prompt_hash,
        requested_at=row.requested_at, responded_at=row.responded_at,
        latency_ms=row.latency_ms, attempt_count=row.attempt_count,
        outcome_status=row.outcome_status, response_json=row.response_json,
        decision=JudgeDecision.model_validate_json(json.dumps(row.decision_json)),
        input_tokens=row.input_tokens, output_tokens=row.output_tokens,
        provider_request_id=row.provider_request_id, error_category=row.error_category,
    )


async def smoke(judge_run_id: UUID) -> None:
    if get_settings().app_env not in {"development", "test"}:
        raise SystemExit("The validation smoke command is development/test only.")
    with SessionLocal() as session:
        row = session.get(JudgeRunRecord, judge_run_id)
        if row is None:
            raise SystemExit("Judge run not found.")
        pack_row = session.get(EvidencePackRecord, row.evidence_pack_id)
        if pack_row is None:
            raise SystemExit("Evidence Pack not found.")
        try:
            judge = _read_judge(row)
            pack = EvidencePack.model_validate(pack_row.snapshot_json)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    # No live entailment adapter is configured in Phase 6A. Unresolved semantic
    # checks remain unable_to_validate rather than being declared valid.
    audit = await ValidationService().run(judge, pack)
    with SessionLocal() as session:
        persist_validation_run(session, audit)
    print(f"JUDGE RUN\nid: {judge.judge_run_id}\nmodel: {judge.model}")
    print(f"label: {judge.decision.label.value if judge.decision else 'none'}")
    print(f"pack hash: {judge.evidence_pack_hash}")
    if judge.search_guard_bypassed or not judge.search_isolation_verified:
        print("DEVELOPMENT-ONLY: search isolation/model identity unverified; "
              "not a trusted medical judgment.")
    for item in (*audit.result.citation_validations,
                 *audit.result.opposing_citation_validations):
        print(f"\nCITATION {item.evidence_id} ({item.role})")
        print(f"exists: {'yes' if item.exists else 'no'}")
        print(f"numeric: {item.numeric_alignment.value}")
        print(f"scope: {item.scope_alignment.value}")
        print(f"relation: {item.relation_alignment.value}")
        print(f"entailment: {item.entailment_status.value}")
        print(f"issues: {[code.value for code in item.issue_codes]}")
        print(f"warnings: {[code.value for code in item.warnings]}")
    print(f"\nJUDGE VALIDATION\naudit id: {audit.id}")
    print(f"status: {audit.status.value}")
    print(f"fatal issues: {[code.value for code in audit.result.fatal_issue_codes]}")
    print("NO FINAL LENS VERDICT")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate one stored judge run offline")
    parser.add_argument("judge_run_id", type=UUID)
    args = parser.parse_args()
    asyncio.run(smoke(args.judge_run_id))


if __name__ == "__main__":
    main()
