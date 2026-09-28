"""Developer-only CLI: judge a stored Evidence Pack without a final verdict."""

import argparse
import asyncio
from uuid import UUID

from app.adapters.judge import OpenAICompatibleJudgeProvider
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.judging.config import configured_slots
from app.judging.models import JudgeSlot
from app.judging.persistence import persist_judge_runs
from app.judging.service import JudgeService
from app.models.retrieval import EvidencePackRecord
from app.retrieval.models import EvidencePack


def print_search_override_warning(slots: tuple[JudgeSlot, ...]) -> None:
    """Warn before any provider call when this is only a plumbing smoke."""

    if any(slot.search_guard_bypassed for slot in slots):
        print(
            "DEVELOPMENT OVERRIDE:\n"
            "search-enabled model guard bypassed.\n"
            "This run validates judging plumbing only and must not be treated as a "
            "verified same-evidence evaluation.",
            flush=True,
        )


async def smoke(pack_id: UUID) -> None:
    settings = get_settings()
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("The judge smoke command is development/test only.")
    try:
        slots = configured_slots(settings)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not slots:
        raise SystemExit("Configure at least one JUDGE_N_PROVIDER/MODEL/MODEL_FAMILY slot.")
    with SessionLocal() as session:
        record = session.get(EvidencePackRecord, pack_id)
        if record is None:
            raise SystemExit("Evidence Pack not found.")
        pack = EvidencePack.model_validate(record.snapshot_json)
        if record.snapshot_hash != pack.snapshot_hash or record.claim_id != pack.claim_id:
            raise SystemExit("Stored Evidence Pack identity mismatch.")
    provider = OpenAICompatibleJudgeProvider(settings.judge_attempt_timeout_seconds)
    service = JudgeService(
        providers={"miri": provider, "openai_compatible": provider},
        attempt_timeout_seconds=settings.judge_attempt_timeout_seconds,
        total_timeout_seconds=settings.judge_total_timeout_seconds,
        concurrency_limit=settings.judge_concurrency_limit,
    )
    allow_override = (settings.app_env in {"development", "test"}
                      and settings.judge_allow_same_family_development)
    print_search_override_warning(slots)
    runs, summary = await service.run(
        pack_id, pack, slots, allow_same_family=allow_override,
        app_env=settings.app_env,
        allow_search_enabled_development=settings.judge_allow_search_enabled_development,
    )
    with SessionLocal() as session:
        persist_judge_runs(session, runs)
    print(f"EVIDENCE PACK\nid: {pack_id}\nhash: {pack.snapshot_hash}")
    for run in runs:
        print(f"\nJUDGE {run.slot}")
        print(f"family: {run.model_family}\nmodel: {run.model}\nprovider: {run.provider}")
        print(f"search_override_active: {run.search_override_active} | "
              f"search_guard_bypassed: {run.search_guard_bypassed} | "
              f"search_isolation_verified: {run.search_isolation_verified}")
        print(f"status: {run.outcome_status}\nlatency_ms: {run.latency_ms}")
        if run.decision:
            print(f"label: {run.decision.label.value}")
            print(f"citations: {', '.join(run.decision.cited_evidence_ids)}")
            print(f"opposing: {', '.join(run.decision.opposing_evidence_ids)}")
            print(f"reason: {run.decision.reasoning_summary}")
        else:
            print(f"failure: {run.error_category}")
    print("\nAGREEMENT SUMMARY (descriptive only)")
    print(f"successful: {summary.successful_judges}/{summary.total_judges}")
    counts = {label.value: count for label, count in summary.label_counts.items()}
    print(f"label counts: {counts}")
    print(f"unanimous: {summary.unanimous}")
    print("NO FINAL VERDICT")


def main() -> None:
    parser = argparse.ArgumentParser(description="Judge a stored frozen Evidence Pack")
    parser.add_argument("evidence_pack_id", type=UUID)
    args = parser.parse_args()
    asyncio.run(smoke(args.evidence_pack_id))


if __name__ == "__main__":
    main()
