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
        MembershipType(
            "student", validity_days=365, loan_period_days=14, loan_limit=5, max_renewals=1, daily_fee=Decimal("2.00")
        ),
        MembershipType(
            "academic", validity_days=365, loan_period_days=30, loan_limit=10, max_renewals=2, daily_fee=Decimal("1.00")
        ),
        MembershipType(
            "staff", validity_days=365, loan_period_days=21, loan_limit=7, max_renewals=2, daily_fee=Decimal("1.00")
        ),
        MembershipType(
            "guest", validity_days=90, loan_period_days=7, loan_limit=2, max_renewals=0, daily_fee=Decimal("5.00")
        ),
    )
}


def initial_valid_until(membership_type: str, start: datetime.date) -> datetime.date:
    """LIB-MEM-03: the membership covers the validity period including the first day."""
    return start + datetime.timedelta(days=MEMBERSHIP_TYPES[membership_type].validity_days - 1)
