"""Working-day rules (LIB-COM-05 to LIB-COM-10). Shared by every module (LIB-CORE-07)."""

import datetime

from lms.core.settings import Settings


def is_weekend(day: datetime.date) -> bool:
    return day.weekday() >= 5  # Saturday, Sunday


def is_holiday(day: datetime.date, settings: Settings) -> bool:
    return day in settings.holidays


def is_working_day(day: datetime.date, settings: Settings) -> bool:
    return not is_weekend(day) and not is_holiday(day, settings)


def next_working_day_on_or_after(day: datetime.date, settings: Settings) -> datetime.date:
    while not is_working_day(day, settings):
        day += datetime.timedelta(days=1)
    return day


def add_working_days(day: datetime.date, days: int, settings: Settings) -> datetime.date:
    if days < 1:
        raise ValueError("days must be at least 1")
    current = day
    counted = 0
    while counted < days:
        current += datetime.timedelta(days=1)
        if is_working_day(current, settings):
            counted += 1
    return current


def working_days_between(start: datetime.date, end: datetime.date, settings: Settings) -> int:
    """Working days x with start < x <= end; 0 when end <= start."""
    if end <= start:
        return 0
    count = 0
    current = start
    while current < end:
        current += datetime.timedelta(days=1)
        if is_working_day(current, settings):
            count += 1
    return count
