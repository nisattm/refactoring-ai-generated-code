"""Uniform error responses (LIB-COM-25 to LIB-COM-27)."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..core.errors import ApiError

log = logging.getLogger("lms")


def error_response(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(_: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        fields = []
        for e in exc.errors():
            loc = [str(p) for p in e["loc"] if p not in ("body", "query", "path")]
            fields.append({"field": ".".join(loc), "problem": e["msg"]})
        return error_response(422, "VALIDATION_ERROR", "Request validation failed", {"fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return error_response(404, "NOT_FOUND", "Resource not found")
        if exc.status_code == 405:
            return error_response(405, "METHOD_NOT_ALLOWED", "Method not allowed")
        return error_response(exc.status_code, "BUSINESS_RULE_VIOLATION", str(exc.detail))

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.exception("unexpected error")
        return error_response(500, "INTERNAL_ERROR", "Internal server error")
