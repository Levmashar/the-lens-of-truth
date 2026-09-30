"""Developer-only explicit-run aggregation; never exposes a public verdict API."""

import argparse
from uuid import UUID

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.retrieval import EvidencePackRecord
from app.verdict.models import AggregationInput, AggregationMode, LensVerdict
from app.verdict.persistence import (
    load_aggregation_context,
    parse_id_list,
    persist_verdict_run,
)
from app.verdict.policy import POLICY_V1, POLICY_V2, POLICY_V3
from app.verdict.service import VerdictService


def smoke(
    pack_id: UUID, judge_run_ids: tuple[UUID, ...],
    validation_run_ids: tuple[UUID, ...], mode: AggregationMode,
    policy_version: str = POLICY_V3.version,
) -> None:
    if get_settings().app_env not in {"development", "test"}:
        raise SystemExit("The verdict smoke command is development/test only.")
    with SessionLocal() as session:
        pack_row = session.get(EvidencePackRecord, pack_id)
        if pack_row is None:
            raise SystemExit("Evidence Pack not found.")
        pack_hash = pack_row.snapshot_hash
        policies = {item.version: item for item in (POLICY_V1, POLICY_V2, POLICY_V3)}
        policy = policies[policy_version]
        request = AggregationInput(
            claim_id=pack_row.claim_id, evidence_pack_id=pack_row.id,
            evidence_pack_hash=pack_row.snapshot_hash,
            judge_run_ids=judge_run_ids,
            judge_validation_run_ids=validation_run_ids,
            mode=mode, policy_version=policy.version,
        )
        context = load_aggregation_context(session, request)
        result = VerdictService(policy=policy).aggregate(request, context)
        record = persist_verdict_run(session, result)
        audit_id = record.id
    print(f"CLAIM\n{context.pack.claim_snapshot.raw_text if context.pack else '(unavailable)'}")
    print(f"\nPACK\nid: {pack_id}\nhash: {pack_hash}")
    print(f"\nPOLICY\n{result.policy_version}\nmode: {mode.value}")
    for item in result.judge_qualifications:
        print(f"\nJUDGE slot {item.slot}: {item.judge_run_id}")
        print(f"qualified: {'yes' if item.qualified else 'no'}")
        print(f"validation: {item.validation_status.value if item.validation_status else 'none'}")
        print(f"label: {item.label.value if item.label else 'none'}")
        print(f"excluded: {[reason.value for reason in item.exclusion_reasons]}")
    counts = {label.value: count for label, count in result.validated_label_counts.items()}
    print(f"\nAGGREGATION\nqualified judges: {result.qualified_judges}")
    print(f"excluded judges: {result.excluded_judges}\nvalidated labels: {counts}")
    print(f"reason codes: {[code.value for code in result.reason_codes]}")
    print(f"semantic hash: {result.semantic_hash}\naudit id: {audit_id}")
    print(f"\nVERDICT: {result.verdict.value.replace('_', ' ').title()}")
    print(f"PRODUCTION QUALIFIED: {str(result.production_qualified).lower()}")
    if mode == AggregationMode.FIXTURE_OR_EVALUATION:
        print("EVALUATION ONLY: This is not a production-qualified medical verdict.")
    if result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY:
        print("No medical conclusion was issued.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate explicitly named stored audit runs")
    parser.add_argument("--pack", required=True, type=UUID)
    parser.add_argument("--judge-runs", required=True,
                        help="Comma-separated judge run UUIDs; empty for no-results pack")
    parser.add_argument("--validation-runs", required=True,
                        help="Comma-separated validation UUIDs; empty for no-results pack")
    parser.add_argument("--mode", choices=[item.value for item in AggregationMode],
                        default=AggregationMode.PRODUCTION.value)
    parser.add_argument("--policy-version", choices=(POLICY_V1.version, POLICY_V2.version,
                                                      POLICY_V3.version),
                        default=POLICY_V3.version)
    args = parser.parse_args()
    smoke(args.pack, parse_id_list(args.judge_runs),
          parse_id_list(args.validation_runs), AggregationMode(args.mode),
          args.policy_version)


if __name__ == "__main__":
    main()
