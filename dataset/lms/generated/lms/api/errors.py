"""Exception handlers producing the common error body (LIB-COM-25 to LIB-COM-27, LIB-API-02)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from lms.core.errors import ApiError

logger = logging.getLogger("lms")

_STATUS_CODES = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "BUSINESS_RULE_VIOLATION",
    415: "VALIDATION_ERROR",
    422: "VALIDATION_ERROR",
}


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_body(code, message, details), headers=headers)


def _field_name(loc: tuple[Any, ...]) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header", "cookie")]
    if parts:
        return ".".join(parts)
    return str(loc[0]) if loc else "body"


def _validation_fields(exc: RequestValidationError) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    seen: set[str] = set()
    for err in exc.errors():
        name = _field_name(tuple(err.get("loc", ())))
        if name in seen:  # one entry per invalid field
            continue
        seen.add(name)
        fields.append({"field": name, "problem": str(err.get("msg", "invalid value"))})
    return fields


async def _handle_api_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return error_response(422, "VALIDATION_ERROR", "Request validation failed", {"fields": _validation_fields(exc)})


async def _handle_http_exception(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    status = exc.status_code
    if status >= 500:
        return error_response(status, "INTERNAL_ERROR", "Internal server error")
    code = _STATUS_CODES.get(status, "BUSINESS_RULE_VIOLATION" if status >= 400 else "INTERNAL_ERROR")
    message = {404: "Resource not found", 405: "Method not allowed"}.get(status, str(exc.detail))
    details: dict[str, Any] = {"fields": []} if code == "VALIDATION_ERROR" else {}
    return error_response(status, code, message, details, headers=dict(exc.headers) if exc.headers else None)


async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error", exc_info=exc)
    return error_response(500, "INTERNAL_ERROR", "Internal server error")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
