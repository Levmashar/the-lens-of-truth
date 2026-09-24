"""Development-only PubMed retrieval preview contract."""

from uuid import UUID

from pydantic import BaseModel

from app.retrieval.models import EvidencePack, RetrievalDiagnostics


class EvidencePreviewRequest(BaseModel):
    analysis_id: UUID
    claim_id: UUID


class EvidencePreviewResponse(BaseModel):
    evidence_pack: EvidencePack
    diagnostics: RetrievalDiagnostics
