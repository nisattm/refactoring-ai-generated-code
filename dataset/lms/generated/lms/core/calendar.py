"""Working-day calendar (LIB-COM-05 to LIB-COM-10)."""

from __future__ import annotations

import datetime
from collections.abc import Container

_ONE_DAY = datetime.timedelta(days=1)


def day_reason(day: datetime.date, holidays: Container[datetime.date]) -> str | None:
    """``"holiday"``, ``"weekend"`` or ``None`` for a working day. Holiday wins over weekend."""
    if day in holidays:
        return "holiday"
    if day.weekday() >= 5:
        return "weekend"
    return None


def is_working_day(day: datetime.date, holidays: Container[datetime.date]) -> bool:
    return day_reason(day, holidays) is None


def next_working_day(day: datetime.date, holidays: Container[datetime.date]) -> datetime.date:
    """LIB-COM-08."""
    while not is_working_day(day, holidays):
        day += _ONE_DAY
    return day


def add_working_days(day: datetime.date, count: int, holidays: Container[datetime.date]) -> datetime.date:
    """LIB-COM-09: ``day`` itself is never counted."""
    remaining = count
    while remaining > 0:
        day += _ONE_DAY
        if is_working_day(day, holidays):
            remaining -= 1
    return day


def working_days_between(
    start: datetime.date, end: datetime.date, holidays: Container[datetime.date]
) -> int:
    """LIB-COM-10: number of working days x with start < x <= end; 0 if end <= start."""
    total = 0
    day = start
    while day < end:
        day += _ONE_DAY
        if is_working_day(day, holidays):
            total += 1
    return total
