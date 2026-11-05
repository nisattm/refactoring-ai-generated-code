"""Error responses in the common format (LIB-COM-25 to LIB-COM-27, LIB-CORE-09)."""

import logging
import typing

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from lms.core.errors import ApiError

logger = logging.getLogger("lms")

_LOCATION_PREFIXES = ("body", "query", "path", "header", "cookie")

_HTTP_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: typing.Mapping[str, typing.Any] | None = None,
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": dict(details or {})}}
    return JSONResponse(status_code=status_code, content=body)


def _field_path(loc: typing.Sequence[typing.Any]) -> str:
    """Dotted path of an invalid field, without the request location (query, body, ...)."""
    parts = loc[1:] if loc and loc[0] in _LOCATION_PREFIXES and len(loc) > 1 else loc
    return ".".join(str(part) for part in parts)


def install_error_handlers(app: FastAPI) -> None:
    # Handlers are plain `def` functions: the API is synchronous (LIB-TECH-06).

    @app.exception_handler(ApiError)
    def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": _field_path(error["loc"]), "problem": error["msg"]}
            for error in exc.errors()
        ]
        return error_response(
            422,
            "VALIDATION_ERROR",
            "The request is invalid.",
            {"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    def _unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        # LIB-COM-27: the response carries no internal details; the traceback goes to the log only.
        logger.error("Unhandled error", exc_info=exc)
        return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")
