"""Map persisted, redacted claims into a retrieval-only snapshot."""

from pydantic import TypeAdapter

from app.medical.entities import MedicalEntity
from app.models.claim import Claim
from app.pipeline.claim_types import legacy_claim_type
from app.pipeline.pico import NormalizedPico, normalize_stored_pico
from app.retrieval.models import ClaimSnapshot

_entities_adapter: TypeAdapter[tuple[MedicalEntity, ...]] = TypeAdapter(tuple[MedicalEntity, ...])


def snapshot_claim(claim: Claim) -> ClaimSnapshot:
    pico = (
        NormalizedPico.model_validate(claim.pico_json) if claim.pico_json
        else normalize_stored_pico(
            raw_text=claim.raw_text, claim_type=claim.claim_type,
            population=claim.population,
            intervention_or_exposure=claim.intervention_or_exposure,
            comparator=claim.comparator, outcome=claim.outcome, timeframe=claim.timeframe,
        )
    )
    return ClaimSnapshot(
        claim_id=claim.id, raw_text=claim.raw_text, normalized_text=claim.normalized_text,
        claim_type=legacy_claim_type(claim.claim_type), pico=pico,
        entities=_entities_adapter.validate_python(claim.linked_entities or []),
    )
