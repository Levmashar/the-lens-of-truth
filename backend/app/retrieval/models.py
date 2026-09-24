"""Typed, frozen contracts for retrieval and evidence snapshots."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.medical.entities import MedicalEntity
from app.pipeline.claim_types import ClaimType
from app.pipeline.pico import NormalizedPico


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ClaimSnapshot(FrozenModel):
    claim_id: UUID
    raw_text: str
    normalized_text: str | None = None
    claim_type: ClaimType | None = None
    pico: NormalizedPico | None = None
    entities: tuple[MedicalEntity, ...] = ()


class RetrievalQuery(FrozenModel):
    query_id: str
    family: Literal["mesh", "lexical", "relation", "distinctive"]
    query: str
    source_fields: tuple[str, ...]
    relation_semantics: ClaimType | None = None


class QueryPlan(FrozenModel):
    version: Literal["1.0"] = "1.0"
    source: Literal["pubmed"] = "pubmed"
    claim_type: ClaimType | None = None
    queries: tuple[RetrievalQuery, ...]
    warnings: tuple[str, ...] = ()


class AbstractSection(FrozenModel):
    label: str | None = None
    text: str


class PubMedDocument(FrozenModel):
    document_id: str
    pmid: str
    title: str
    abstract: str | None = None
    abstract_sections: tuple[AbstractSection, ...] = ()
    journal: str | None = None
    publication_date: date | None = None
    authors: tuple[str, ...] = ()
    doi: str | None = None
    publication_types: tuple[str, ...] = ()
    mesh_terms: tuple[str, ...] = ()
    language: str | None = None
    canonical_url: str
    retrieved_at: datetime
    content_sha256: str
    query_ids: tuple[str, ...] = ()


class EvidencePassage(FrozenModel):
    passage_id: str
    document_id: str
    text: str
    section: str
    char_start: int | None = None
    char_end: int | None = None
    content_sha256: str


class RankedPassage(FrozenModel):
    evidence_id: str
    passage: EvidencePassage
    rank: int = Field(ge=1)
    retrieval_score: float = Field(ge=0, le=1)
    factors: dict[str, float]


class RetrievalDiagnostics(FrozenModel):
    status: Literal["ok", "no_results", "partial_metadata"]
    query_count: int
    cache_hits: int = 0
    pmids_found: int = 0
    documents_returned: int = 0
    missing_pmids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class QueryExecution(FrozenModel):
    query_id: str
    pmids: tuple[str, ...]
    cache_hit: bool


class EvidencePack(FrozenModel):
    evidence_pack_version: Literal["1.0"] = "1.0"
    claim_id: UUID
    claim_snapshot: ClaimSnapshot
    query_plan: QueryPlan
    documents: tuple[PubMedDocument, ...]
    passages: tuple[RankedPassage, ...]
    retrieved_at: datetime
    snapshot_hash: str


class RetrievalResult(FrozenModel):
    pack: EvidencePack
    diagnostics: RetrievalDiagnostics
    query_executions: tuple[QueryExecution, ...]
