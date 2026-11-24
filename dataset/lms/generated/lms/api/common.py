"""Helpers shared by the endpoint modules: clock, roles, ownership, query dates and request bodies."""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from lms.auth.deps import Principal
from lms.core.clock import local_now
from lms.core.errors import Forbidden, ValidationFailed
from lms.core.timeutil import parse_date
from lms.members.models import Member

DATE_PROBLEM = "expected a valid date in the form YYYY-MM-DD"


def request_now(request: Request) -> datetime.datetime:
    """The local date-time of the application clock (LIB-COM-02)."""
    return local_now(request.app.state.settings.clock)


# --- roles and ownership -----------------------------------------------------------------------


def is_member(principal: Principal) -> bool:
    return principal.user.role == "member"


def is_staff(principal: Principal) -> bool:
    return principal.user.role != "member"


def ensure_own_or_staff(principal: Principal, member_id: int, what: str) -> None:
    """LIB-AUTH-25: a member may only address their own ``what``."""
    if is_member(principal) and principal.user.member_id != member_id:
        raise Forbidden(f"Only your own {what} can be accessed")


def own_member_id(principal: Principal) -> int:
    """The member id behind a ``member`` user."""
    member_id = principal.user.member_id
    if member_id is None:
        raise Forbidden("The authenticated user has no member record")
    return member_id


def acting_member_id(principal: Principal, requested: int | None, action: str) -> int:
    """The member a request acts for: members act for themselves and must not send ``member_id``
    (``action`` completes "members ... and must not send member_id"); staff must name the member."""
    if is_member(principal):
        if requested is not None:
            raise ValidationFailed.single("member_id", f"members {action} and must not send member_id")
        return own_member_id(principal)
    if requested is None:
        raise ValidationFailed.single("member_id", "member_id is required for librarians and admins")
    return requested


def own_member(db: Session, principal: Principal) -> Member:
    """The member record behind a ``member`` user."""
    member = db.get(Member, principal.user.member_id) if principal.user.member_id is not None else None
    if member is None:
        raise Forbidden("The authenticated user has no member record")
    return member


# --- query dates ---------------------------------------------------------------------------------


def optional_date(name: str, raw: str | None) -> datetime.date | None:
    """A date query parameter that may be absent; an unparsable value is a validation error."""
    if raw is None:
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        raise ValidationFailed.single(name, DATE_PROBLEM) from None


def collect_date(
    name: str, raw: str | None, problems: list[dict[str, str]], *, required: bool = True
) -> datetime.date | None:
    """Parse a date query parameter and collect its problem, so that several can be reported together."""
    if raw is None:
        if required:
            problems.append({"field": name, "problem": "field required"})
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        problems.append({"field": name, "problem": DATE_PROBLEM})
        return None


def report_range(first: str | None, to: str | None, max_days: int = 365) -> tuple[datetime.date, datetime.date]:
    """The required ``from`` / ``to`` query parameters of a report, checked as a range."""
    problems: list[dict[str, str]] = []
    start = collect_date("from", first, problems)
    end = collect_date("to", to, problems)
    if problems:
        raise ValidationFailed(problems)
    assert start is not None and end is not None
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days > max_days:
        raise ValidationFailed.single("to", "the range must not be longer than 366 days including both ends")
    return start, end


# --- request bodies ----------------------------------------------------------------------------


def fields_of(body: BaseModel) -> dict[str, Any]:
    """The parsed values of a request body (``model_dump`` would serialize amounts to strings)."""
    return {name: getattr(body, name) for name in type(body).model_fields}
