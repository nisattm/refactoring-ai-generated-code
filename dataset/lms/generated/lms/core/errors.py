"""Error type and helpers shared by all modules (LIB-COM-25 to LIB-COM-29)."""
from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


class ValidationFailed(ApiError):
    def __init__(self, fields: list[dict[str, str]]):
        super().__init__(422, "VALIDATION_ERROR", "Request validation failed", {"fields": fields})


def validation_error(field: str, problem: str) -> ValidationFailed:
    return ValidationFailed([{"field": field, "problem": problem}])


def not_found(field: str | None = None, id: Any = None, message: str = "Resource not found") -> ApiError:
    details = {} if field is None else {"field": field, "id": id}
    return ApiError(404, "NOT_FOUND", message, details)


def conflict(message: str = "Conflict", details: dict[str, Any] | None = None) -> ApiError:
    return ApiError(409, "CONFLICT", message, details)


def business_rule(
    code: str = "BUSINESS_RULE_VIOLATION",
    message: str = "Business rule violated",
    details: dict[str, Any] | None = None,
) -> ApiError:
    return ApiError(409, code, message, details)


def forbidden(message: str = "Forbidden") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)
