"""Validated medical-entity output shared by linking and API contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal[
    "population", "intervention_or_exposure", "comparator", "outcome",
    "disease", "drug", "measurement", "other",
]
MatchType = Literal["exact", "synonym", "fuzzy", "unresolved"]


class MedicalEntityCandidate(BaseModel):
    """An unassigned terminology suggestion, never a verified claim fact."""

    model_config = ConfigDict(extra="forbid")

    mesh_id: str
    preferred_name: str
    match_type: MatchType
    confidence: float = Field(ge=0, le=1)
    terminology_source: Literal["mesh"] = "mesh"
    terminology_version: str
    terminology_sha256: str | None = None
    tree_numbers: tuple[str, ...] = ()


class MedicalEntity(BaseModel):
    """A source-grounded mention; identifiers are absent until confidently linked."""

    model_config = ConfigDict(extra="forbid")

    surface_text: str = Field(min_length=1)
    entity_type: EntityType
    umls_cui: str | None = None
    umls_version: str | None = None
    mesh_id: str | None = None
    preferred_name: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    match_type: MatchType = "unresolved"
    ambiguous: bool = False
    terminology_source: Literal["mesh", "umls"] | None = None
    terminology_version: str | None = None
    terminology_sha256: str | None = None
    tree_numbers: tuple[str, ...] = ()
    candidates: tuple[MedicalEntityCandidate, ...] = ()
