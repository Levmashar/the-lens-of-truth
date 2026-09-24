"""FastAPI application factory."""

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


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the API without connecting to external services at import time."""

    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level)
    app = FastAPI(title=runtime_settings.app_name, version="0.1.0")

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
