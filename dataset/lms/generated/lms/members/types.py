"""Membership types (section 7.1)."""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal


@dataclasses.dataclass(frozen=True)
class MembershipType:
    value: str
    validity_days: int
    loan_period_days: int
    loan_limit: int
    max_renewals: int
    daily_fee: Decimal


MEMBERSHIP_TYPES: dict[str, MembershipType] = {
    t.value: t
    for t in (
        MembershipType("student", 365, 14, 5, 1, Decimal("2.00")),
        MembershipType("academic", 365, 30, 10, 2, Decimal("1.00")),
        MembershipType("staff", 365, 21, 7, 2, Decimal("1.00")),
        MembershipType("guest", 90, 7, 2, 0, Decimal("5.00")),
    )
}


def initial_valid_until(membership_type: str, start: datetime.date) -> datetime.date:
    """LIB-MEM-03: the membership covers the validity period including the first day."""
    return start + datetime.timedelta(days=MEMBERSHIP_TYPES[membership_type].validity_days - 1)
