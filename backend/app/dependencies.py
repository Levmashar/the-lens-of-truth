"""Composition root for replaceable Phase 2 adapters."""

from typing import Annotated

from fastapi import Depends

from app.adapters.claim_extractor import (
    ClaimExtractorAdapter,
    DisabledClaimExtractor,
    MiriClaimExtractor,
    OpenAICompatibleClaimExtractor,
)
from app.adapters.ocr import TesseractOcrAdapter
from app.adapters.pubmed import PubMedAdapter, RedisQueryCache
from app.adapters.storage import LocalFilesystemUploadStorage
from app.core.config import Settings, get_settings
from app.medical.linker import MedicalEntityLinker
from app.medical.mesh import IndexedMeshProvider, UnconfiguredMeshProvider
from app.medical.umls import UnconfiguredUmlsProvider
from app.services.analysis_ingestion import AnalysisIngestionService
from app.services.redaction import PiiRedactor


def get_upload_storage(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LocalFilesystemUploadStorage:
    """Build the private local-storage adapter for development and container use."""

    return LocalFilesystemUploadStorage(root=settings.upload_storage_path)


def get_ocr_adapter(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TesseractOcrAdapter:
    """Build the local bounded OCR adapter."""

    return TesseractOcrAdapter(
        executable=settings.ocr_executable,
        timeout_seconds=settings.ocr_timeout_seconds,
    )


def get_claim_extractor(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClaimExtractorAdapter:
    """Select an explicitly configured semantic extraction provider."""

    if settings.claim_extractor_provider == "disabled":
        return DisabledClaimExtractor()
    api_key = settings.claim_extractor_api_key
    if settings.claim_extractor_provider == "miri":
        if not settings.claim_extractor_base_url:
            return DisabledClaimExtractor()
        return MiriClaimExtractor(
            service_name="miri_chatgpt_claim_extractor",
            timeout_seconds=settings.claim_extractor_timeout_seconds,
            total_timeout_seconds=settings.claim_extractor_total_timeout_seconds,
            base_url=settings.claim_extractor_base_url,
            model=settings.claim_extractor_model or "chatgpt-auto",
            api_key=api_key.get_secret_value() if api_key else None,
        )
    if not (
        settings.claim_extractor_base_url
        and settings.claim_extractor_model
        and api_key is not None
        and api_key.get_secret_value()
    ):
        return DisabledClaimExtractor()
    return OpenAICompatibleClaimExtractor(
        service_name="openai_compatible_claim_extractor",
        timeout_seconds=settings.claim_extractor_timeout_seconds,
        total_timeout_seconds=settings.claim_extractor_total_timeout_seconds,
        base_url=settings.claim_extractor_base_url,
        model=settings.claim_extractor_model,
        api_key=api_key.get_secret_value(),
    )


def build_analysis_ingestion_service(
    *,
    settings: Settings,
    storage: LocalFilesystemUploadStorage,
    ocr: TesseractOcrAdapter,
    extractor: ClaimExtractorAdapter,
) -> AnalysisIngestionService:
    """Compose the narrow Phase 2 orchestration service for API or maintenance work."""

    return AnalysisIngestionService(
        storage=storage,
        ocr=ocr,
        extractor=extractor,
        redactor=PiiRedactor(),
        retention_hours=settings.upload_retention_hours,
        maximum_claims=settings.claim_extractor_max_claims,
        upload_max_bytes=settings.upload_max_bytes,
        upload_max_pixels=settings.upload_max_pixels,
        entity_linker=build_entity_linker(settings),
    )


def build_entity_linker(settings: Settings) -> MedicalEntityLinker:
    """Use an imported NLM release when installed; UMLS remains optional."""

    mesh = (
        IndexedMeshProvider(settings.mesh_index_path)
        if settings.mesh_index_path.is_file() else UnconfiguredMeshProvider()
    )
    return MedicalEntityLinker(umls=UnconfiguredUmlsProvider(), mesh=mesh)


def get_analysis_ingestion_service(
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[LocalFilesystemUploadStorage, Depends(get_upload_storage)],
    ocr: Annotated[TesseractOcrAdapter, Depends(get_ocr_adapter)],
    extractor: Annotated[ClaimExtractorAdapter, Depends(get_claim_extractor)],
) -> AnalysisIngestionService:
    """Compose the narrow Phase 2 orchestration service for API routes."""

    return build_analysis_ingestion_service(
        settings=settings,
        storage=storage,
        ocr=ocr,
        extractor=extractor,
    )


def get_pubmed_adapter(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PubMedAdapter:
    """Build the official NCBI adapter only when a contact email is configured."""

    from app.core.errors import ExternalCapabilityError

    if not settings.ncbi_email:
        raise ExternalCapabilityError(
            code="pubmed_not_configured",
            message="PubMed retrieval requires an NCBI contact email.",
        )
    api_key = settings.ncbi_api_key
    return PubMedAdapter(
        tool=settings.ncbi_tool, email=settings.ncbi_email,
        api_key=api_key.get_secret_value() if api_key else None,
        timeout_seconds=settings.pubmed_timeout_seconds,
        max_retries=settings.pubmed_max_retries,
        minimum_interval_seconds=0.36,
        retmax=settings.pubmed_query_retmax,
        cache=RedisQueryCache(settings.redis_url),
        cache_ttl_seconds=settings.pubmed_cache_ttl_seconds,
    )
