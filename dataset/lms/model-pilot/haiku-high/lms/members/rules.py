"""Membership types and validity (section 7.1, LIB-MEM-02, LIB-MEM-03, LIB-MEM-04, LIB-MEM-09)."""

import datetime

from lms.core.errors import field_problem

GUEST = "guest"

# Section 7.1: length of one membership period in calendar days.
PERIOD_DAYS: dict[str, int] = {"student": 365, "academic": 365, "staff": 365, "guest": 90}


def type_problems(
    membership_type: str, phone: str | None, university_id: str | None
) -> list[dict[str, str]]:
    """LIB-MEM-02: the type-specific fields. One problem per invalid field; empty when valid."""
    problems: list[dict[str, str]] = []
    if membership_type == GUEST:
        if phone is None:
            problems.append(field_problem("phone", "is required for guests"))
        if university_id is not None:
            problems.append(field_problem("university_id", "must be empty for guests"))
    elif university_id is None:
        problems.append(field_problem("university_id", "is required for this membership type"))
    return problems


def first_valid_until(start: datetime.date, membership_type: str) -> datetime.date:
    """LIB-MEM-03: the period includes its first day, so it ends PERIOD_DAYS - 1 days after the start."""
    return start + datetime.timedelta(days=PERIOD_DAYS[membership_type] - 1)


def renewed_valid_until(
    valid_until: datetime.date, today: datetime.date, membership_type: str
) -> datetime.date:
    """LIB-MEM-09: extend a current membership by one period; restart an expired one from today."""
    if valid_until >= today:
        return valid_until + datetime.timedelta(days=PERIOD_DAYS[membership_type])
    return first_valid_until(today, membership_type)


def membership_valid_on(status: str, valid_until: datetime.date, day: datetime.date) -> bool:
    """LIB-MEM-04: active and not after the end of the membership."""
    return status == "active" and day <= valid_until


def format_member_no(member_id: int) -> str:
    """LIB-MEM-01 / section 7.2: "M" followed by the id padded to six digits."""
    return f"M{member_id:06d}"
