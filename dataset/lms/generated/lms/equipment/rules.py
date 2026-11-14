"""Constants and time rules of module 16 (sections 24.1 to 24.3, LIB-EQ-15, LIB-EQ-22, LIB-EQ-23)."""

from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Container
from decimal import Decimal

from lms.core.calendar import add_working_days
from lms.core.clock import LOCAL_TZ
from lms.core.money import quantize
from lms.staff.schedule import BranchSchedule

DESK_OPENS = datetime.time(8, 0)
DESK_CLOSES = datetime.time(20, 0)
DEFAULT_SCHEDULE = BranchSchedule()
DUE_TIME_WORKING_DAYS = datetime.time(17, 0)
GRACE = datetime.timedelta(minutes=15)
HOLD_EARLY = datetime.timedelta(minutes=15)
COLLECT_LATE = datetime.timedelta(minutes=30)
MIN_LEAD = datetime.timedelta(minutes=30)
MAX_AHEAD_DAYS = 14
HALF_HOUR = datetime.timedelta(minutes=30)
TRAINING_VALID_DAYS = 364
DEBT_BLOCK = Decimal("50.00")
LATE_FEE_VALUE_CAP = Decimal("0.20")

FAR_FUTURE = datetime.datetime(9999, 12, 31, tzinfo=datetime.timezone.utc)

LENDABLE_STATUSES = ("available", "on_loan")


@dataclasses.dataclass(frozen=True)
class EquipmentRules:
    """One row of the table in 24.3."""

    open_loans: int
    reservations: int
    training_needed: bool


EQUIPMENT_RULES: dict[str, EquipmentRules] = {
    "student": EquipmentRules(2, 2, True),
    "academic": EquipmentRules(3, 3, False),
    "staff": EquipmentRules(3, 3, False),
    "guest": EquipmentRules(0, 0, False),
}


def at_local(day: datetime.date, time: datetime.time) -> datetime.datetime:
    return datetime.datetime.combine(day, time, LOCAL_TZ)


def desk_open(
    t: datetime.datetime, holidays: Container[datetime.date], schedule: BranchSchedule = DEFAULT_SCHEDULE
) -> bool:
    """LIB-EQ-01 with the hours and closures of the branch (LIB-STF-09); the default schedule is 08:00-20:00."""
    local = t.astimezone(LOCAL_TZ)
    return schedule.is_calendar_open(local.date(), holidays) and schedule.opens_at <= local.time() < schedule.closes_at


def next_desk_opening(
    t: datetime.datetime, holidays: Container[datetime.date], schedule: BranchSchedule = DEFAULT_SCHEDULE
) -> datetime.datetime:
    """LIB-EQ-02: for a moment at which the desk is closed."""
    local = t.astimezone(LOCAL_TZ)
    day = local.date()
    if schedule.is_calendar_open(day, holidays) and local.time() < schedule.opens_at:
        return at_local(day, schedule.opens_at)
    day += datetime.timedelta(days=1)
    while not schedule.is_calendar_open(day, holidays):
        day += datetime.timedelta(days=1)
    return at_local(day, schedule.opens_at)


def due_at_from(
    start: datetime.datetime, period_unit: str, period: int, holidays: Container[datetime.date]
) -> datetime.datetime:
    """LIB-EQ-15 (and LIB-EQ-19 with the current ``due_at`` as ``start``)."""
    local = start.astimezone(LOCAL_TZ)
    if period_unit == "hours":
        return min(local + datetime.timedelta(hours=period), at_local(local.date(), DESK_CLOSES))
    return at_local(add_working_days(local.date(), period, holidays), DUE_TIME_WORKING_DAYS)


def is_overdue(due_at: datetime.datetime, now: datetime.datetime) -> bool:
    """LIB-EQ-16."""
    return now > due_at + GRACE


def late_hours_between(due_at: datetime.datetime, at: datetime.datetime) -> int:
    """LIB-EQ-22."""
    if at <= due_at + GRACE:
        return 0
    return -((due_at - at) // datetime.timedelta(hours=1))  # ceiling of the elapsed hours


def late_fee_amount(late_hours: int, hourly_late_fee: Decimal, value: Decimal) -> Decimal:
    """LIB-EQ-23: ``min(late_hours × hourly_late_fee, 20 % of value)``, rounded once."""
    if late_hours <= 0:
        return Decimal("0.00")
    return quantize(min(late_hours * hourly_late_fee, value * LATE_FEE_VALUE_CAP))


def valid_training_until(completed_on: datetime.date) -> datetime.date:
    return completed_on + datetime.timedelta(days=TRAINING_VALID_DAYS)
