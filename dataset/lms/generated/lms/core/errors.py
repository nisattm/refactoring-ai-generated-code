"""Application errors (LIB-COM-25 to LIB-COM-29). Handlers are registered by ``lms.api``."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """An error that becomes ``{"error": {"code", "message", "details"}}``."""

    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details: dict[str, Any] = details or {}


class Unauthenticated(ApiError):
    status_code = 401
    code = "UNAUTHENTICATED"


class Forbidden(ApiError):
    status_code = 403
    code = "FORBIDDEN"


class NotFound(ApiError):
    status_code = 404
    code = "NOT_FOUND"


class Conflict(ApiError):
    status_code = 409
    code = "CONFLICT"


class BusinessRuleViolation(ApiError):
    status_code = 409
    code = "BUSINESS_RULE_VIOLATION"


class ValidationFailed(ApiError):
    status_code = 422
    code = "VALIDATION_ERROR"

    def __init__(self, fields: list[dict[str, str]], message: str = "Request validation failed") -> None:
        super().__init__(message, details={"fields": fields})

    @classmethod
    def single(cls, field: str, problem: str) -> ValidationFailed:
        return cls([{"field": field, "problem": problem}])


def reference_not_found(field: str, value: Any) -> NotFound:
    """LIB-COM-29: a referenced entity does not exist."""
    return NotFound(f"{field} {value} does not exist", details={"field": field, "id": value})
