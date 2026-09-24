"""Import all models so Alembic can discover their metadata."""

from app.models.claim import Claim
from app.models.evaluation import FinalVerdict, ModelEvaluation
from app.models.evidence import EvidenceDocument, EvidencePassage
from app.models.retrieval import (
    EvidencePackRecord,
    RetrievalDocumentQuery,
    RetrievalQuery,
    RetrievalRun,
)
from app.models.screenshot_upload import ScreenshotUpload
from app.models.submission import Submission

__all__ = [
    "Claim",
    "EvidenceDocument",
    "EvidencePassage",
    "EvidencePackRecord",
    "RetrievalDocumentQuery",
    "RetrievalQuery",
    "RetrievalRun",
    "FinalVerdict",
    "ModelEvaluation",
    "ScreenshotUpload",
    "Submission",
]
