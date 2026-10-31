"""Working-day arithmetic (LIB-COM-05 to LIB-COM-10)."""
import datetime
from collections.abc import Set

_ONE = datetime.timedelta(days=1)


def is_working_day(d: datetime.date, holidays: Set[datetime.date]) -> bool:
    return d.weekday() < 5 and d not in holidays


def day_reason(d: datetime.date, holidays: Set[datetime.date]) -> str | None:
    if d in holidays:
        return "holiday"
    if d.weekday() >= 5:
        return "weekend"
    return None


def next_working_day(d: datetime.date, holidays: Set[datetime.date]) -> datetime.date:
    while not is_working_day(d, holidays):
        d += _ONE
    return d


def add_working_days(d: datetime.date, n: int, holidays: Set[datetime.date]) -> datetime.date:
    count = 0
    while count < n:
        d += _ONE
        if is_working_day(d, holidays):
            count += 1
    return d


def working_days_between(a: datetime.date, b: datetime.date, holidays: Set[datetime.date]) -> int:
    count = 0
    d = a
    while d < b:
        d += _ONE
        if is_working_day(d, holidays):
            count += 1
    return count
