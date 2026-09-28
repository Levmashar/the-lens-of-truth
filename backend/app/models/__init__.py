"""Import all models so Alembic can discover their metadata."""

from app.models.claim import Claim
from app.models.evaluation import FinalVerdict, ModelEvaluation
from app.models.evidence import EvidenceDocument, EvidencePassage
from app.models.judge_run import JudgeRunRecord
from app.models.judge_validation_run import JudgeValidationRunRecord
from app.models.report_run import ReportRunRecord
from app.models.retrieval import (
    EvidencePackRecord,
    RetrievalDocumentQuery,
    RetrievalQuery,
    RetrievalRun,
)
from app.models.screenshot_upload import ScreenshotUpload
from app.models.submission import Submission
from app.models.verdict_run import VerdictRunRecord

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
    "JudgeRunRecord",
    "JudgeValidationRunRecord",
    "ReportRunRecord",
    "ScreenshotUpload",
    "Submission",
    "VerdictRunRecord",
]
