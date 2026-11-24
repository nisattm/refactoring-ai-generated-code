"""Constants and time rules of module 21 (sections 29.2, LIB-CRS-25, LIB-CRS-29)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from decimal import Decimal

from lms.core.clock import LOCAL_TZ
from lms.core.money import ZERO
from lms.staff.schedule import BranchSchedule

MAX_ITEMS = 40
DEBT_BLOCK = Decimal("50.00")
LATE_GRACE_MINUTES = 5
LATE_FEE_CAP = Decimal("30.00")

# 29.2: open reserve loans at a time, by membership type.
RESERVE_LOAN_LIMITS: dict[str, int] = {"student": 2, "academic": 3, "staff": 0, "guest": 0}

# LIB-CRS-29: (unit of a started period in minutes, fee per started period).
LATE_FEE_RATES: dict[str, tuple[int, Decimal]] = {
    "2h": (60, Decimal("1.00")),
    "1d": (1440, Decimal("5.00")),
    "3d": (1440, Decimal("5.00")),
}

OPEN_DAYS_AFTER_TODAY: dict[str, int] = {"1d": 1, "3d": 3}
TWO_HOURS = datetime.timedelta(hours=2)


def at_local(day: datetime.date, time: datetime.time) -> datetime.datetime:
    return datetime.datetime.combine(day, time, LOCAL_TZ)


def due_at_for(
    now: datetime.datetime, loan_period: str, schedule: BranchSchedule, holidays: Container[datetime.date]
) -> datetime.datetime:
    """LIB-CRS-25. Open days and hours are those of ``schedule`` (LIB-STF-14, LIB-STF-07)."""
    local = now.astimezone(LOCAL_TZ)
    if loan_period == "2h":
        return min(local + TWO_HOURS, at_local(local.date(), schedule.closes_at))
    remaining = OPEN_DAYS_AFTER_TODAY[loan_period]
    day = local.date()
    while remaining > 0:
        day += datetime.timedelta(days=1)
        if schedule.is_calendar_open(day, holidays):
            remaining -= 1
    return at_local(day, schedule.closes_at)


def late_minutes_between(due_at: datetime.datetime, at: datetime.datetime) -> int:
    """Whole minutes from ``due_at`` to ``at``, at least 0."""
    return max(0, (at - due_at) // datetime.timedelta(minutes=1))


def late_fee_amount(loan_period: str, late_minutes: int) -> Decimal:
    """LIB-CRS-29."""
    if late_minutes <= LATE_GRACE_MINUTES:
        return ZERO
    unit, rate = LATE_FEE_RATES[loan_period]
    started = -(-late_minutes // unit)
    return min(started * rate, LATE_FEE_CAP)
