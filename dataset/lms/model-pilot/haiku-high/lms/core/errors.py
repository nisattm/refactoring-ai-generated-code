"""Error type shared by all modules (LIB-COM-25, LIB-COM-26)."""

import typing


class ApiError(Exception):
    """An error response: HTTP status, error code, message and optional details.

    Endpoints raise this instead of returning error responses, so that the
    request's transaction is rolled back (LIB-TECH-08).
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: typing.Mapping[str, typing.Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = dict(details or {})


def field_problem(field: str, problem: str) -> dict[str, str]:
    return {"field": field, "problem": problem}


def validation_error(*problems: dict[str, str]) -> ApiError:
    """422 VALIDATION_ERROR with one entry per invalid field."""
    return ApiError(
        422,
        "VALIDATION_ERROR",
        "The request is invalid.",
        {"fields": list(problems)},
    )
