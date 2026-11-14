"""Constants and small helpers of module 15 (sections 23.2 and 23.6)."""

from __future__ import annotations

import dataclasses
import datetime
from decimal import ROUND_HALF_UP, Decimal

NO_SHOW_GRACE = datetime.timedelta(minutes=15)
CHECK_IN_EARLY = datetime.timedelta(minutes=10)
LATE_CANCELLATION_WINDOW = datetime.timedelta(hours=2)
NO_SHOW_FEE = Decimal("10.00")
INCIDENT_BAN_THRESHOLD = 3
INCIDENT_WINDOW_DAYS = 30
INCIDENT_BAN_DAYS = 14
DEBT_BLOCK = Decimal("50.00")

ACTIVE_STATUSES = ("booked", "checked_in")
QUOTA_STATUSES = ("booked", "checked_in", "completed", "no_show")
SYSTEM_CANCEL_REASONS = ("member_deactivated", "member_banned", "room_closed", "not_enough_participants", "branch_closed")


@dataclasses.dataclass(frozen=True)
class RoomRules:
    """One row of the table in 23.2."""

    daily_hours: int
    weekly_hours: int
    ahead_days: int | None
    future_limit: int


ROOM_RULES: dict[str, RoomRules] = {
    "student": RoomRules(2, 6, 7, 2),
    "academic": RoomRules(4, 12, 14, 4),
    "staff": RoomRules(3, 9, 14, 3),
    "guest": RoomRules(0, 0, None, 0),
}


def format_hours(minutes: int) -> str:
    """Hours with one decimal place (``ROUND_HALF_UP``), for example ``"2.5"``."""
    return format((Decimal(minutes) / 60).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "f")


def week_start(day: datetime.date) -> datetime.date:
    """Weeks run Monday to Sunday."""
    return day - datetime.timedelta(days=day.weekday())


def minutes_between(start: datetime.time, end: datetime.time) -> int:
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
