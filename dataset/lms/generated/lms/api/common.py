"""Helpers shared by the routers: ownership checks (LIB-AUTH-25), query dates and request bodies."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel

from lms.auth.deps import Principal
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, ValidationFailed
from lms.core.timeutil import parse_date
from lms.members.models import Member

MAX_REPORT_DAYS = 365
DATE_PROBLEM ="expected a valid date in the form YYYY-MM-DD"


def require_own_or_staff(principal: Principal, member_id: int, message: str) -> None:
    """LIB-AUTH-25: a ``member`` user may only address their own data; staff may address any."""
    if principal.user.role == "member" and principal.user.member_id != member_id:
        raise Forbidden(message)


def own_member_id(principal: Principal) -> int:
    """The id of the member behind a ``member`` user."""
    member_id = principal.user.member_id
    if member_id is None:
        raise Forbidden("The authenticated user has no member record")
    return member_id


def own_member(db: SessionDep, principal: Principal) -> Member:
    """The member behind a ``member`` user."""
    member = db.get(Member, principal.user.member_id) if principal.user.member_id is not None else None
    if member is None:
        raise Forbidden("The authenticated user has no member record")
    return member


def optional_date(name: str, raw: str | None) -> datetime.date | None:
    """A query date that may be absent; ``422`` if it is present but invalid."""
    if raw is None:
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        raise ValidationFailed.single(name, DATE_PROBLEM) from None


def date_param(
    name: str, raw: str | None, problems: list[dict[str, str]], *, required: bool = False
) -> datetime.date | None:
    """A query date; its problem is appended to ``problems`` so that several can be reported together."""
    if raw is None:
        if required:
            problems.append({"field": name, "problem": "field required"})
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        problems.append({"field": name, "problem": DATE_PROBLEM})
        return None


def required_range(first: str | None, to: str | None) -> tuple[datetime.date, datetime.date]:
    """The required ``from`` and ``to`` query dates, ``from`` not after ``to``."""
    problems: list[dict[str, str]] = []
    start = date_param("from", first, problems, required=True)
    end = date_param("to", to, problems, required=True)
    if problems:
        raise ValidationFailed(problems)
    assert start is not None and end is not None
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    return start, end


def report_range(first: str | None, to: str | None) -> tuple[datetime.date, datetime.date]:
    """The date range of a report: ``from`` and ``to`` are required and span at most 366 days."""
    start, end = required_range(first, to)
    if (end - start).days > MAX_REPORT_DAYS:
        raise ValidationFailed.single("to", "the range must not be longer than 366 days including both ends")
    return start, end


def patch_fields(body: BaseModel) -> dict[str, Any]:
    """The fields that are present in a PATCH body, with their parsed values."""
    return {name: getattr(body, name) for name in body.model_fields_set}


def fields_of(body: BaseModel) -> dict[str, Any]:
    """The parsed values of a request body (``model_dump`` would serialize amounts to strings)."""
    return {name: getattr(body, name) for name in type(body).model_fields}
