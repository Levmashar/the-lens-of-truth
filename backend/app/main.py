"""FastAPI application factory."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import router as api_router
from app.core.config import Settings, get_settings
from app.core.errors import (
    LensError,
    handle_http_error,
    handle_lens_error,
    handle_unexpected_error,
    handle_validation_error,
)
from app.core.logging import configure_logging
from app.core.request_context import RequestContextMiddleware
from app.db.session import SessionLocal
from app.maintenance import purge_expired_uploads

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run raw-upload retention cleanup without placing sensitive data in logs."""

    settings: Settings = app.state.settings
    if settings.app_env == "test":
        yield
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(_retention_cleanup_loop(stop_event, settings))
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _retention_cleanup_loop(stop_event: asyncio.Event, settings: Settings) -> None:
    """Purge at startup and at a bounded interval, including during idle periods."""

    while not stop_event.is_set():
        try:
            with SessionLocal() as session:
                removed = await purge_expired_uploads(session=session, settings=settings)
            if removed:
                logger.info("Expired upload records purged", extra={"count": removed})
        except Exception:
            logger.error("Retention cleanup failed")
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.retention_cleanup_interval_seconds
            )
        except TimeoutError:
            continue


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the API without connecting to external services at import time."""

    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level)
    app = FastAPI(title=runtime_settings.app_name, version="0.1.0", lifespan=_lifespan)
    app.state.settings = runtime_settings

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key", "X-Request-ID"],
    )
    app.add_exception_handler(LensError, handle_lens_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)

    @app.get("/healthz", tags=["health"])
    async def healthcheck(request: Request) -> JSONResponse:
        """Liveness check; dependency readiness is intentionally separate."""

        return JSONResponse(
            content={
                "status": "ok",
                "service": "the-lens-of-truth-api",
                "environment": runtime_settings.app_env,
                "request_id": str(request.state.request_id),
            }
        )

    app.include_router(api_router, prefix=runtime_settings.api_v1_prefix)
    return app


app = create_app()
