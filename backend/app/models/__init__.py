"""Import all models so Alembic can discover their metadata."""

from app.models.claim import Claim
from app.models.evaluation import FinalVerdict, ModelEvaluation
from app.models.evidence import EvidenceDocument, EvidencePassage
from app.models.submission import Submission

__all__ = [
    "Claim",
    "EvidenceDocument",
    "EvidencePassage",
    "FinalVerdict",
    "ModelEvaluation",
    "Submission",
]
