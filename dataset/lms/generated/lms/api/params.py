"""Helpers of the endpoints for query parameters: dates, report ranges and ownership of member data."""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from lms.auth.deps import Principal
from lms.core.errors import Forbidden, ValidationFailed
from lms.core.limits import MAX_REPORT_DAYS
from lms.core.timeutil import parse_date
from lms.members.models import Member

DATE_PROBLEM = "expected a valid date in the form YYYY-MM-DD"
NO_MEMBER_RECORD = "The authenticated user has no member record"


def optional_date(name: str, raw: str | None) -> datetime.date | None:
    """A date query parameter that may be missing; an invalid one is a ``422`` for ``name``."""
    if raw is None:
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        raise ValidationFailed.single(name, DATE_PROBLEM) from None


def collect_date(
    name: str, raw: str | None, problems: list[dict[str, str]], *, required: bool = True
) -> datetime.date | None:
    """Parse a date query parameter, adding what is wrong with it to ``problems`` instead of raising."""
    if raw is None:
        if required:
            problems.append({"field": name, "problem": "field required"})
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        problems.append({"field": name, "problem": DATE_PROBLEM})
        return None


def report_range(first: str | None, to: str | None) -> tuple[datetime.date, datetime.date]:
    """The required ``from`` and ``to`` of a report: both valid, ordered and at most 366 days apart."""
    problems: list[dict[str, str]] = []
    start = collect_date("from", first, problems)
    end = collect_date("to", to, problems)
    if problems:
        raise ValidationFailed(problems)
    assert start is not None and end is not None
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days > MAX_REPORT_DAYS:
        raise ValidationFailed.single("to", "the range must not be longer than 366 days including both ends")
    return start, end


def reject_nulls(
    fields: dict[str, Any], names: Iterable[str] | None = None, *, allow: Iterable[str] = ()
) -> None:
    """``422`` for every sent field that is ``null``; only ``names`` are checked if given, ``allow`` may be null."""
    checked = fields if names is None else {name: fields[name] for name in names if name in fields}
    nulls = [name for name, value in checked.items() if value is None and name not in allow]
    if nulls:
        raise ValidationFailed([{"field": name, "problem": "value must not be null"} for name in nulls])


def require_own_or_staff(principal: Principal, member_id: int, message: str) -> None:
    """LIB-AUTH-25: a member may only address their own data (``403`` with ``message`` otherwise)."""
    if principal.user.role == "member" and principal.user.member_id != member_id:
        raise Forbidden(message)


def own_member_id(principal: Principal) -> int:
    """The id of the member record behind a ``member`` user."""
    member_id = principal.user.member_id
    if member_id is None:
        raise Forbidden(NO_MEMBER_RECORD)
    return member_id


def own_member(db: Session, principal: Principal) -> Member:
    """The member record behind a ``member`` user."""
    member = db.get(Member, principal.user.member_id) if principal.user.member_id is not None else None
    if member is None:
        raise Forbidden(NO_MEMBER_RECORD)
    return member
