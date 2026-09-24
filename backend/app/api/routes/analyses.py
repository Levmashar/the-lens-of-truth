"""Mock analysis endpoints that establish the Phase 1 API contract."""

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, status
from fastapi.responses import StreamingResponse

from app.schemas.analysis import AnalysisAccepted, AnalysisDetail, CreateAnalysisRequest

router = APIRouter()


@router.post("", response_model=AnalysisAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    _request: CreateAnalysisRequest,
    _idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AnalysisAccepted:
    """Accept an analysis request without starting the future medical pipeline."""

    return AnalysisAccepted(analysis_id=uuid4(), status="processing")


@router.get("/{analysis_id}", response_model=AnalysisDetail)
async def get_analysis(analysis_id: UUID) -> AnalysisDetail:
    """Return the explicit mock state until persistence/orchestration exists."""

    return AnalysisDetail.processing(analysis_id)


async def _mock_events(analysis_id: UUID) -> AsyncIterator[str]:
    stages = (
        {"stage": "accepted", "progress": 0.0, "mock": True},
        {"stage": "awaiting_pipeline", "progress": 0.0, "mock": True},
    )
    for event in stages:
        yield f"event: stage\ndata: {json.dumps(event)}\n\n"
    completed = {"analysis_id": str(analysis_id), "mock": True}
    yield f"event: completed\ndata: {json.dumps(completed)}\n\n"


@router.get("/{analysis_id}/events")
async def get_analysis_events(analysis_id: UUID) -> StreamingResponse:
    """Expose a valid SSE contract with clearly marked mock events."""

    return StreamingResponse(_mock_events(analysis_id), media_type="text/event-stream")
