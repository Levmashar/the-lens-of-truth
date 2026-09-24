"""Top-level API router."""

from fastapi import APIRouter

from app.api.routes.analyses import router as analyses_router

router = APIRouter()
router.include_router(analyses_router, prefix="/analyses", tags=["analyses"])
