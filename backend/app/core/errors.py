"""Error types and safe HTTP exception handlers."""

import logging
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    """Public error body; it deliberately excludes internal details."""

    code: str
    message: str
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class LensError(Exception):
    """Expected application error with a safe public representation."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class UploadValidationError(LensError):
    """A screenshot failed server-side safety validation."""

    def __init__(
        self, *, code: str, message: str, status_code: int = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    ) -> None:
        super().__init__(status_code=status_code, code=code, message=message)


class ExternalCapabilityError(LensError):
    """A required configured adapter is unavailable or returned unusable output."""

    def __init__(
        self, *, code: str, message: str, status_code: int = status.HTTP_503_SERVICE_UNAVAILABLE
    ) -> None:
        super().__init__(status_code=status_code, code=code, message=message)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def _response(*, status_code: int, code: str, message: str, request: Request) -> JSONResponse:
    payload = ErrorEnvelope(
        error=ErrorBody(code=code, message=message, request_id=_request_id(request))
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


async def handle_lens_error(request: Request, exc: Exception) -> JSONResponse:
    """Render known domain errors without exposing implementation details."""

    if not isinstance(exc, LensError):
        return await handle_unexpected_error(request, exc)

    return _response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        request=request,
    )


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    """Provide a stable validation contract while keeping raw input out of logs."""

    if not isinstance(exc, RequestValidationError):
        return await handle_unexpected_error(request, exc)

    return _response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="request_validation_failed",
        message="Request validation failed.",
        request=request,
    )


async def handle_http_error(request: Request, exc: Exception) -> JSONResponse:
    """Normalize framework HTTP errors to the public error envelope."""

    if not isinstance(exc, HTTPException):
        return await handle_unexpected_error(request, exc)

    detail: Any = exc.detail
    message = detail if isinstance(detail, str) else "Request could not be completed."
    return _response(
        status_code=exc.status_code,
        code="http_error",
        message=message,
        request=request,
    )


async def handle_unexpected_error(request: Request, _exc: Exception) -> JSONResponse:
    """Log unexpected failures with a correlation ID, never exception text to clients."""

    logger.exception("Unhandled API error", extra={"request_id": _request_id(request)})
    return _response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_server_error",
        message="An unexpected server error occurred.",
        request=request,
    )
