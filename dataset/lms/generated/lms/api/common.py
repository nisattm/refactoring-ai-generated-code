"""Helpers shared by the routers: request context, ownership check and patch bodies."""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import Request
from pydantic import BaseModel

from lms.auth.deps import Principal
from lms.core.clock import local_now, today
from lms.core.errors import Forbidden, ValidationFailed
from lms.core.settings import Settings
from lms.core.timeutil import parse_date

CSV_TYPE = "text/csv; charset=utf-8"


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def now_of(request: Request) -> datetime.datetime:
    """Current local date-time of the application's clock."""
    return local_now(settings_of(request).clock)


def today_of(request: Request) -> datetime.date:
    """LIB-COM-02: today's local date."""
    return today(settings_of(request).clock)


def require_own_member(principal: Principal, member_id: int, what: str) -> None:
    """LIB-AUTH-25: a ``member`` user may only address their own ``what``."""
    if principal.user.role == "member" and principal.user.member_id != member_id:
        raise Forbidden(f"Only your own {what} can be accessed")


def optional_date(name: str, raw: str | None) -> datetime.date | None:
    """An optional ``YYYY-MM-DD`` query parameter; an unparsable value is a ``422 VALIDATION_ERROR``."""
    if raw is None:
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        raise ValidationFailed.single(name, "expected a valid date in the form YYYY-MM-DD") from None


def provided_fields(body: BaseModel) -> dict[str, Any]:
    """The fields that were present in a PATCH body."""
    return {name: getattr(body, name) for name in body.model_fields_set}
