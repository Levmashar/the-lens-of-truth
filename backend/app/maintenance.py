"""Retention maintenance invoked by the API lifespan and deployment scheduler."""

from sqlalchemy.orm import Session

from app.adapters.claim_extractor import DisabledClaimExtractor
from app.adapters.ocr import TesseractOcrAdapter
from app.adapters.storage import LocalFilesystemUploadStorage
from app.core.config import Settings
from app.dependencies import build_analysis_ingestion_service
from app.services.analysis_ingestion import AnalysisIngestionService


def build_retention_service(settings: Settings) -> AnalysisIngestionService:
    """Build only what raw-upload cleanup needs; semantic extraction stays disabled."""

    return build_analysis_ingestion_service(
        settings=settings,
        storage=LocalFilesystemUploadStorage(root=settings.upload_storage_path),
        ocr=TesseractOcrAdapter(
            executable=settings.ocr_executable,
            timeout_seconds=settings.ocr_timeout_seconds,
        ),
        extractor=DisabledClaimExtractor(),
    )


async def purge_expired_uploads(*, session: Session, settings: Settings) -> int:
    """Delete expired raw screenshot objects and short-lived analysis records."""

    return await build_retention_service(settings).purge_expired(session=session)
