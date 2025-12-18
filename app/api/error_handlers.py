"""Common exception handlers for API responses."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BusinessLogicError,
    DuplicateRecordError,
    KHWException,
    LLMHallucinationError,
    LLMRateLimitError,
    LLMValidationError,
    NeedsReReviewError,
    RecordNotFoundError,
    ValidationError,
    VectorIndexError,
    VectorSearchError,
)
from app.api.response_utils import build_meta
from app.schemas.response import ResponseError, ResponseEnvelope


EXCEPTION_RESPONSE_MAP: dict[type[Exception], tuple[int, str]] = {
    RecordNotFoundError: (status.HTTP_404_NOT_FOUND, "RecordNotFoundError"),
    ValidationError: (status.HTTP_400_BAD_REQUEST, "ValidationError"),
    DuplicateRecordError: (status.HTTP_409_CONFLICT, "DuplicateRecordError"),
    NeedsReReviewError: (status.HTTP_409_CONFLICT, "NeedsReReviewError"),
    BusinessLogicError: (status.HTTP_400_BAD_REQUEST, "BusinessLogicError"),
    AuthenticationError: (status.HTTP_401_UNAUTHORIZED, "AuthenticationError"),
    AuthorizationError: (status.HTTP_403_FORBIDDEN, "AuthorizationError"),
    LLMHallucinationError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "LLMHallucinationError"),
    LLMValidationError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "LLMValidationError"),
    LLMRateLimitError: (status.HTTP_429_TOO_MANY_REQUESTS, "LLMRateLimitError"),
    VectorIndexError: (status.HTTP_503_SERVICE_UNAVAILABLE, "VectorIndexError"),
    VectorSearchError: (status.HTTP_503_SERVICE_UNAVAILABLE, "VectorSearchError"),
}
DEFAULT_ERROR_CODE = "INTERNAL.UNEXPECTED"


def register_exception_handlers(app: FastAPI) -> None:
    """Register handlers that wrap exceptions in the common envelope."""

    app.add_exception_handler(KHWException, _khw_exception_handler)
    app.add_exception_handler(RequestValidationError, _request_validation_error_handler)
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)


def _serialize_error(
    *,
    exc: Exception,
    code: str,
    message: str,
    details: Any | None = None,
    hint: str | None = None,
) -> ResponseError:
    return ResponseError(
        code=code,
        message=message,
        details=details,
        hint=hint,
    )


def _compress_detail(detail: Any) -> tuple[str, Any | None]:
    if isinstance(detail, dict):
        message = detail.get("message", str(detail))
        return message, detail.get("details") or detail

    return str(detail), None


def _format_validation_message(errors: list[dict[str, Any]]) -> str:
    if not errors:
        return "Validation error"

    parts: list[str] = []
    for error in errors:
        loc = error.get("loc", [])
        msg = error.get("msg", "Validation error")
        loc_path = ".".join(str(item) for item in loc) if loc else None
        parts.append(f"{loc_path}: {msg}" if loc_path else msg)

    return "; ".join(parts)


async def _khw_exception_handler(request: Request, exc: KHWException) -> JSONResponse:
    status_code, error_code = EXCEPTION_RESPONSE_MAP.get(
        type(exc), (status.HTTP_500_INTERNAL_SERVER_ERROR, DEFAULT_ERROR_CODE)
    )
    meta = build_meta(request)
    message = str(exc)
    details = getattr(exc, "details", None)
    hint = getattr(exc, "hint", None)

    error_payload = _serialize_error(
        exc=exc,
        code=error_code or getattr(exc, "code", DEFAULT_ERROR_CODE),
        message=message,
        details=details,
        hint=hint,
    )

    envelope = ResponseEnvelope[None](
        success=False,
        data=None,
        error=error_payload,
        meta=meta,
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(envelope, by_alias=True),
    )


async def _request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    meta = build_meta(request)
    errors = exc.errors() or []
    message = _format_validation_message(errors)

    envelope = ResponseEnvelope[None](
        success=False,
        data=None,
        error=_serialize_error(
            exc=exc,
            code="ValidationError",
            message=message,
            details={"errors": errors},
            hint=None,
        ),
        meta=meta,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder(envelope, by_alias=True),
    )


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    meta = build_meta(request)
    status_code = exc.status_code
    detail = exc.detail
    message, details = _compress_detail(detail)
    hint = None
    code = getattr(exc, "code", None) or f"HTTP.{status_code}"

    envelope = ResponseEnvelope[None](
        success=False,
        data=None,
        error=_serialize_error(exc=exc, code=code, message=message, details=details, hint=hint),
        meta=meta,
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(envelope, by_alias=True),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    meta = build_meta(request)
    message = "Unexpected server error."
    error_payload = _serialize_error(
        exc=exc,
        code=DEFAULT_ERROR_CODE,
        message=message,
        details=None,
        hint=None,
    )

    envelope = ResponseEnvelope[None](
        success=False,
        data=None,
        error=error_payload,
        meta=meta,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=jsonable_encoder(envelope, by_alias=True),
    )
