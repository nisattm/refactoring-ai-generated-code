"""Error responses in the common format (LIB-COM-25 to LIB-COM-28, LIB-CORE-09)."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Parameter locations FastAPI puts first in a validation error location.
_LOCATIONS = {"query", "path", "body", "header", "cookie"}

_HTTP_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def validation_error(field: str, problem: str) -> ApiError:
    """A single-field 422 VALIDATION_ERROR (LIB-COM-26)."""
    return ApiError(
        422,
        "VALIDATION_ERROR",
        "The request is invalid.",
        {"fields": [{"field": field, "problem": problem}]},
    )


def _body(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": _field_path(error["loc"]), "problem": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            _body("VALIDATION_ERROR", "The request is invalid.", {"fields": fields}),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        message = str(exc.detail)
        return JSONResponse(
            _body(code, message, {}),
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Generic message only; no stack trace or internal detail (LIB-COM-27).
        return JSONResponse(
            _body("INTERNAL_ERROR", "An unexpected error occurred.", {}),
            status_code=500,
        )


def _field_path(loc: tuple[Any, ...]) -> str:
    parts = list(loc)
    if parts and parts[0] in _LOCATIONS:
        parts = parts[1:]
    return ".".join(str(part) for part in parts) or "body"
