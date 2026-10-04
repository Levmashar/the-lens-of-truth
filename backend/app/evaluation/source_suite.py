"""Opt-in fresh public-source controls; not historical analyses or clinical gold."""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.core.config import Settings
from app.dependencies import build_entity_linker
from app.evaluation.artifacts import runtime_directory, save_artifact
from app.orchestration.worker import build_orchestrator
from app.pipeline.claim_types import ClaimType
from app.pipeline.pico import normalize_stored_pico
from app.retrieval.models import ClaimSnapshot

CONTROLS = (
    ("Smoking causes lung cancer.", "Smoking", "lung cancer", "causal", None),
    ("Regularly smoking cigarettes causes lung cancer.", "smoking cigarettes", "lung cancer",
     "causal", None),
    ("Smoking does not cause lung cancer.", "Smoking", "lung cancer", "causal", None),
    ("Frequent sunscreen use causes invasive melanoma.", "Frequent sunscreen use",
     "invasive melanoma", "causal", None),
    ("Frequent sunscreen use causes skin cancer.", "Frequent sunscreen use", "skin cancer",
     "causal", None),
    ("High blood pressure increases stroke risk.", "High blood pressure", "stroke",
     "association", None),
    ("High blood pressure causes cancer.", "High blood pressure", "cancer", "causal", None),
    ("Vitamin C prevents the common cold.", "Vitamin C", "common cold", "prevention", None),
    ("Carrots improve eyesight.", "Carrots", "eyesight", "causal", None),
    ("Regular soy consumption in men increases estrogen levels.", "soy consumption",
     "estrogen levels", "causal", "men"),
    ("Regular soy consumption in men lowers muscle gain.", "soy consumption", "muscle gain",
     "causal", "men"),
)


async def freeze(settings: Settings, limit: int) -> dict[str, Any]:
    if settings.app_env not in {"development", "test"}:
        raise ValueError("Development/test only")
    orchestrator = build_orchestrator(settings)
    claims: list[dict[str, Any]] = []
    for text, exposure, outcome, kind, population in CONTROLS[:limit]:
        pico = normalize_stored_pico(
            raw_text=text, claim_type=ClaimType(kind), population=population,
            intervention_or_exposure=exposure, comparator=None, outcome=outcome, timeframe=None,
        )
        snapshot = ClaimSnapshot(
            claim_id=uuid5(NAMESPACE_URL, f"slice4-public:{text}"), raw_text=text,
            claim_type=ClaimType(kind), pico=pico,
            entities=build_entity_linker(settings).link(pico),
        )
        try:
            async with asyncio.timeout(150):
                retrieved = await orchestrator.retrieve(snapshot)
            pack = retrieved.pack
            claims.append({"pack": {"snapshot_json": pack.model_dump(mode="json")},
                           "retrieval": retrieved.diagnostics.model_dump(mode="json"),
                           "origin": "fresh source-grounded development control"})
            print(str(snapshot.claim_id), len(pack.documents), len(pack.selected_evidence_ids),
                  flush=True)
        except (TimeoutError, ValueError) as exc:
            claims.append({"claim_id": str(snapshot.claim_id), "pack": None,
                           "failure": type(exc).__name__})
    return {"version": "public-controls-1.0", "clinical_qualification": False,
            "origin": "fresh retrieval, not a retained historical analysis",
            "purge_after": (datetime.now(UTC) + timedelta(hours=24)).isoformat(), "claims": claims}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--limit", type=int, default=11)
    parser.add_argument("--runtime", type=Path, default=Path("/app/runtime"))
    args = parser.parse_args()
    if not args.run or not 1 <= args.limit <= 11:
        raise SystemExit("Opt in with --run and bounded --limit 1..11")
    settings = Settings()
    result = asyncio.run(freeze(settings, args.limit))
    print(save_artifact(runtime_directory(args.runtime), "public-controls", result, settings))


if __name__ == "__main__":
    main()
