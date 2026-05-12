"""Unified error envelope for the public API.

Every non-2xx response from /api/v1/* gets the shape:

    {
      "error": {
        "code": "<machine-readable slug>",
        "message": "<human-readable message>",
        "details": <optional dict or list>
      }
    }

Slugs derive from HTTP status; rate-limit, validation and unhandled-server-error
get special-cased codes. Stable enough for external consumers to switch on.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    410: "gone",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


def code_for_status(status_code: int) -> str:
    return _STATUS_CODES.get(status_code, f"http_{status_code}")


def _envelope(
    *,
    status_code: int,
    message: str,
    code: str | None = None,
    details: Any | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = {
        "error": {
            "code": code or code_for_status(status_code),
            "message": message,
        }
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(body, status_code=status_code, headers=headers)


async def _http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        # Endpoint already produced a structured detail dict.
        return _envelope(
            status_code=exc.status_code,
            code=str(detail.get("code")),
            message=str(detail.get("message", "")),
            details=detail.get("details"),
            headers=dict(exc.headers) if exc.headers else None,
        )
    message = detail if isinstance(detail, str) else str(detail or "")
    return _envelope(
        status_code=exc.status_code,
        message=message,
        headers=dict(exc.headers) if exc.headers else None,
    )


async def _validation_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return _envelope(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="validation_error",
        message="Запрос не прошёл валидацию",
        details=exc.errors(),
    )


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _envelope(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="Внутренняя ошибка сервиса",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
