"""Safely re-normalize legacy pending claims using the installed MeSH release."""

import argparse
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.dependencies import build_entity_linker
from app.medical.linker import MedicalEntityLinker
from app.medical.mesh import IndexedMeshProvider
from app.models.claim import Claim
from app.pipeline.completeness import assess_completeness
from app.pipeline.pico import normalization_status, normalize_stored_pico

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RenormalizationCounts:
    updated: int = 0
    skipped: int = 0
    failed: int = 0


def renormalize_claim(claim: Claim, linker: MedicalEntityLinker) -> bool:
    """Mutate only an untouched pending claim; return false when it must be skipped."""

    if (
        claim.normalization_status != "pending"
        or claim.linked_entities is not None
        or claim.pico_json is not None
    ):
        return False
    pico = normalize_stored_pico(
        raw_text=claim.raw_text, claim_type=claim.claim_type,
        population=claim.population, intervention_or_exposure=claim.intervention_or_exposure,
        comparator=claim.comparator, outcome=claim.outcome, timeframe=claim.timeframe,
    )
    entities = linker.link(pico)
    quality = assess_completeness(pico, entities, linker.mesh)
    linked_count = sum(
        entity.mesh_id is not None or entity.umls_cui is not None for entity in entities
    )
    claim.pico_json = pico.model_dump(mode="json")
    claim.linked_entities = [entity.model_dump(mode="json") for entity in entities]
    claim.normalization_quality = quality.model_dump(mode="json")
    claim.normalization_status = normalization_status(
        pico, linked_count=linked_count, mention_count=len(entities), quality=quality
    )
    return True


def renormalize_pending(
    *, session: Session, linker: MedicalEntityLinker, batch_size: int, dry_run: bool,
) -> RenormalizationCounts:
    """Process pending claims in bounded, keyset-ordered batches with row locks."""

    if not 1 <= batch_size <= 1000:
        raise ValueError("batch size must be between 1 and 1000")
    counts = RenormalizationCounts()
    last_id: UUID | None = None
    while True:
        query = (
            select(Claim).where(Claim.normalization_status == "pending")
            .order_by(Claim.id).limit(batch_size).with_for_update(skip_locked=True)
        )
        if last_id is not None:
            query = query.where(Claim.id > last_id)
        claims = list(session.scalars(query))
        if not claims:
            break
        for claim in claims:
            last_id = claim.id
            try:
                with session.begin_nested():
                    changed = renormalize_claim(claim, linker)
                    if changed:
                        session.flush()
                if changed:
                    counts.updated += 1
                else:
                    counts.skipped += 1
            except Exception:
                counts.failed += 1
                logger.exception("Pending claim re-normalization failed for claim_id=%s", claim.id)
        if dry_run:
            session.rollback()
        else:
            session.commit()
        logger.info(
            "Re-normalization progress updated=%d skipped=%d failed=%d dry_run=%s",
            counts.updated, counts.skipped, counts.failed, dry_run,
        )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=100)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview changes (default)")
    mode.add_argument("--apply", action="store_true", help="Commit safe pending updates")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    linker = build_entity_linker(get_settings())
    if not isinstance(linker.mesh, IndexedMeshProvider):
        parser.error("Import and configure an official NLM MeSH index first")
    with SessionLocal() as session:
        counts = renormalize_pending(
            session=session, linker=linker, batch_size=args.batch_size, dry_run=not args.apply,
        )
    logger.info(
        "Re-normalization finished updated=%d skipped=%d failed=%d dry_run=%s",
        counts.updated, counts.skipped, counts.failed, not args.apply,
    )
    if counts.failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
