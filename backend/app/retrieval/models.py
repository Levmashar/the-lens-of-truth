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

    @property
    def standalone_text(self) -> str:
        """The independently readable proposition; raw_text remains the source span."""

        return self.normalized_text or self.raw_text


class RetrievalQuery(FrozenModel):
    query_id: str
    family: Literal[
        "mesh", "lexical", "relation", "distinctive", "endpoint",
        "automatic", "lay_variant",
    ]
    query: str
    source_fields: tuple[str, ...]
    relation_semantics: ClaimType | None = None


class QueryPlan(FrozenModel):
    version: Literal["1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6"] = "1.2"
    source: Literal["pubmed"] = "pubmed"
    claim_type: ClaimType | None = None
    queries: tuple[RetrievalQuery, ...]
    warnings: tuple[str, ...] = ()


class AbstractSection(FrozenModel):
    label: str | None = None
    text: str


IntegrityStatus = Literal[
    "valid", "retracted", "expression_of_concern", "corrected", "updated", "unknown"
]
CheckStatus = Literal["checked", "not_applicable", "not_found", "failed", "unavailable"]
StudyDesign = Literal[
    "systematic_review", "meta_analysis", "randomized_controlled_trial", "clinical_trial",
    "cohort", "case_control", "cross_sectional", "observational", "guideline", "review",
    "case_report", "animal_study", "in_vitro", "editorial_or_commentary", "other", "unknown",
]
RelationshipDirection = Literal["aligned", "reverse", "incidental", "unknown"]


class RelationshipDirectness(FrozenModel):
    """Claim-specific topical relationship fit, never evidence support or truth."""

    score: float = Field(default=0.0, ge=0, le=1)
    direction: RelationshipDirection = "unknown"
    factors: dict[str, float] = Field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class EndpointDirectness(FrozenModel):
    """Whether the claimed outcome is studied, independent of result direction."""

    score: float = Field(default=0.0, ge=0, le=1)
    factors: dict[str, float] = Field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class IntegrityReference(FrozenModel):
    source: Literal["pubmed", "crossref"]
    relation: str
    identifier: str
    identifier_type: Literal["pmid", "doi"]
    signal: IntegrityStatus | None = None
    assertion_source: str | None = None


class IntegrityCheck(FrozenModel):
    source: Literal["pubmed", "crossref"]
    status: CheckStatus
    checked_at: datetime | None = None
    version: str
    failure_type: str | None = None


class DocumentIntegrity(FrozenModel):
    status: IntegrityStatus = "unknown"
    sources: tuple[str, ...] = ()
    checked_at: datetime | None = None
    check_version: str = "integrity-1"
    warnings: tuple[str, ...] = ()
    references: tuple[IntegrityReference, ...] = ()
    checks: tuple[IntegrityCheck, ...] = ()


class CrossrefEnrichment(FrozenModel):
    check: IntegrityCheck
    doi: str | None = None
    work_type: str | None = None
    publisher: str | None = None
    published_date: date | None = None
    deposited_date: date | None = None
    references: tuple[IntegrityReference, ...] = ()


DocumentPurpose = Literal[
    "causal_assessment", "systematic_evidence_summary", "clinical_guideline",
    "public_health_guidance", "patient_information", "fact_sheet", "research_report",
    "press_release", "other",
    "transmission_assessment",
]


class RelationshipAnalysis(FrozenModel):
    """Claim-exposure design, not the publication/container design."""

    analysis_design: Literal[
        "randomized_intervention", "secondary_observational_analysis", "prospective_cohort",
        "case_control", "cross_sectional", "systematic_review", "meta_analysis", "unknown",
        "diagnostic_accuracy",
    ] = "unknown"
    exposure_assignment: Literal["randomized", "observed", "synthesized", "unknown"] = "unknown"
    basis: str = "not_established"
    evidence_text: str | None = None


class AuthoritativeMetadata(FrozenModel):
    source_id: str
    organization: str
    document_purpose: DocumentPurpose
    last_verified_at: datetime
    updated_at: date | None = None
    content_version: str
    currency: Literal["current", "stale", "unknown"]
    availability: Literal["available"] = "available"
    summary_source: bool = True
    underlying_studies_known: bool = False
    reference_urls: tuple[str, ...] = ()
    underlying_pmids: tuple[str, ...] = ()
    independence_group: str
    attribution: str
    extraction_version: str = "approved-html-1.0"
    retained_block_count: int = 0
    omitted_block_count: int = 0


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
    integrity: DocumentIntegrity = Field(default_factory=DocumentIntegrity)
    crossref: CrossrefEnrichment | None = None
    metadata_provenance: dict[str, str] = Field(default_factory=dict)
    study_design: StudyDesign = "unknown"
    study_design_source: str = "unclassified"
    quality_prior: float = Field(default=0.4, ge=0, le=1)
    quality_factors: dict[str, float] = Field(default_factory=dict)
    applicability_warnings: tuple[str, ...] = ()
    relationship_directness: RelationshipDirectness = Field(
        default_factory=RelationshipDirectness
    )
    endpoint_directness: EndpointDirectness = Field(default_factory=EndpointDirectness)
    # Common frozen document envelope; authoritative documents have no PMID ("").
    source_kind: Literal["pubmed", "authoritative_public_health"] = "pubmed"
    authoritative: AuthoritativeMetadata | None = None
    relationship_analysis: RelationshipAnalysis | None = None
    evidence_role_hint: Literal["direct", "contextual", "incompatible"] | None = None


class PubMedFetchResult(FrozenModel):
    documents: tuple[PubMedDocument, ...]
    seen_pmids: tuple[str, ...] = ()
    incomplete_pmids: tuple[str, ...] = ()
    unsupported_pmids: tuple[str, ...] = ()


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
    passage_type: Literal["title", "abstract"] | None = None
    relationship_directness: RelationshipDirectness = Field(
        default_factory=RelationshipDirectness
    )
    endpoint_directness: EndpointDirectness = Field(default_factory=EndpointDirectness)
    selection_priority_score: float = Field(default=0.0, ge=0, le=1)
    selection_factors: dict[str, float] = Field(default_factory=dict)
    selected_for_judging: bool = False
    selection_reason: Literal[
        "relevant_abstract", "title_only", "title_unique_relevance", "background_fallback",
        "retracted_excluded", "nonhuman_evidence_excluded", "insufficient_claim_focus",
        "endpoint_indirect_when_direct_alternatives_exist",
        "non_evidence_publication_excluded", "nonclinical_visual_context_excluded",
        "post_disease_endpoint_excluded", "indirect_relationship_question_excluded",
        "title_only_when_abstract_available", "direct_title_evidence_available",
        "unstated_active_comparator_excluded",
        "specific_outcome_endpoint_absent_excluded",
        "exposure_arm_population_mismatch_excluded",
        "contextual_relevance",
        "direct_assessment_relevance",
    ] | None = None


class RetrievalDiagnostics(FrozenModel):
    status: Literal["ok", "no_results", "partial_metadata"]
    query_count: int
    cache_hits: int = 0
    pmids_found: int = 0
    documents_returned: int = 0
    missing_pmids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    reason_counts: dict[str, int] = Field(default_factory=dict)
    integrity_status_counts: dict[str, int] = Field(default_factory=dict)
    crossref_status_counts: dict[str, int] = Field(default_factory=dict)
    doi_coverage: int = 0
    search_executions: tuple["QueryExecution", ...] = ()
    authoritative_statuses: dict[str, str] = Field(default_factory=dict)


class QueryExecution(FrozenModel):
    query_id: str
    pmids: tuple[str, ...]
    cache_hit: bool
    actual_query: str | None = None
    sort: str | None = None
    retmax: int | None = None
    total_count: int | None = None
    returned_count: int | None = None


class EvidencePack(FrozenModel):
    evidence_pack_version: Literal["1.0", "1.1", "1.2", "1.3", "1.4", "1.5"] = "1.4"
    claim_id: UUID
    claim_snapshot: ClaimSnapshot
    query_plan: QueryPlan
    documents: tuple[PubMedDocument, ...]
    passages: tuple[RankedPassage, ...]
    selected_evidence_ids: tuple[str, ...] = ()
    retrieved_at: datetime
    snapshot_hash: str


class RetrievalResult(FrozenModel):
    pack: EvidencePack
    diagnostics: RetrievalDiagnostics
    query_executions: tuple[QueryExecution, ...]
