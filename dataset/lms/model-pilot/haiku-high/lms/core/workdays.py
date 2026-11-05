"""Working-day calendar (LIB-COM-05 to LIB-COM-10, LIB-CORE-02 to LIB-CORE-07).

Every function takes the holiday set explicitly so that all modules use
`Settings.holidays` and get identical results.
"""

import datetime
import typing

_FIRST_WEEKEND_DAY = 5  # datetime.weekday() values: Monday is 0, Saturday is 5

# LIB-COM-06 / section 3.2: default official holidays, 2026-2027.
_DEFAULT_HOLIDAY_TABLE: tuple[tuple[datetime.date, str], ...] = (
    (datetime.date(2026, 1, 1), "New Year's Day"),
    (datetime.date(2026, 3, 20), "Ramazan Bayramı, day 1"),
    (datetime.date(2026, 3, 21), "Ramazan Bayramı, day 2"),
    (datetime.date(2026, 3, 22), "Ramazan Bayramı, day 3"),
    (datetime.date(2026, 4, 23), "National Sovereignty and Children's Day"),
    (datetime.date(2026, 5, 1), "Labour and Solidarity Day"),
    (datetime.date(2026, 5, 19), "Commemoration of Atatürk, Youth and Sports Day"),
    (datetime.date(2026, 5, 27), "Kurban Bayramı, day 1"),
    (datetime.date(2026, 5, 28), "Kurban Bayramı, day 2"),
    (datetime.date(2026, 5, 29), "Kurban Bayramı, day 3"),
    (datetime.date(2026, 5, 30), "Kurban Bayramı, day 4"),
    (datetime.date(2026, 7, 15), "Democracy and National Unity Day"),
    (datetime.date(2026, 8, 30), "Victory Day"),
    (datetime.date(2026, 10, 29), "Republic Day"),
    (datetime.date(2027, 1, 1), "New Year's Day"),
    (datetime.date(2027, 3, 9), "Ramazan Bayramı, day 1"),
    (datetime.date(2027, 3, 10), "Ramazan Bayramı, day 2"),
    (datetime.date(2027, 3, 11), "Ramazan Bayramı, day 3"),
    (datetime.date(2027, 4, 23), "National Sovereignty and Children's Day"),
    (datetime.date(2027, 5, 1), "Labour and Solidarity Day"),
    (datetime.date(2027, 5, 16), "Kurban Bayramı, day 1"),
    (datetime.date(2027, 5, 17), "Kurban Bayramı, day 2"),
    (datetime.date(2027, 5, 18), "Kurban Bayramı, day 3"),
    (
        datetime.date(2027, 5, 19),
        "Kurban Bayramı, day 4; Commemoration of Atatürk, Youth and Sports Day",
    ),
    (datetime.date(2027, 7, 15), "Democracy and National Unity Day"),
    (datetime.date(2027, 8, 30), "Victory Day"),
    (datetime.date(2027, 10, 29), "Republic Day"),
)

DEFAULT_HOLIDAYS: frozenset[datetime.date] = frozenset(d for d, _ in _DEFAULT_HOLIDAY_TABLE)

# Names of the default holidays. Holidays supplied through Settings.holidays
# that are not in this table have no name.
HOLIDAY_NAMES: typing.Mapping[datetime.date, str] = dict(_DEFAULT_HOLIDAY_TABLE)

# LIB-CORE-05: largest span accepted by working-days-between.
MAX_BETWEEN_DAYS = 3660


def _is_weekend(day: datetime.date) -> bool:
    return day.weekday() >= _FIRST_WEEKEND_DAY


def day_reason(day: datetime.date, holidays: typing.AbstractSet[datetime.date]) -> str | None:
    """Why a day is not a working day: "holiday", "weekend", or None for a working day.

    A date that is both a weekend and a holiday has reason "holiday" (LIB-CORE-02).
    """
    if day in holidays:
        return "holiday"
    if _is_weekend(day):
        return "weekend"
    return None


def is_working_day(day: datetime.date, holidays: typing.AbstractSet[datetime.date]) -> bool:
    """LIB-COM-05: not a Saturday, not a Sunday, not an official holiday."""
    return day_reason(day, holidays) is None


def next_working_day(day: datetime.date, holidays: typing.AbstractSet[datetime.date]) -> datetime.date:
    """LIB-COM-08: `day` if it is a working day, otherwise the first working day after it."""
    current = day
    while not is_working_day(current, holidays):
        current += datetime.timedelta(days=1)
    return current


def add_working_days(
    day: datetime.date, days: int, holidays: typing.AbstractSet[datetime.date]
) -> datetime.date:
    """LIB-COM-09: the date on which `days` working days after `day` have been counted (days >= 1)."""
    if days < 1:
        raise ValueError("days must be at least 1")
    current = day
    counted = 0
    while counted < days:
        current += datetime.timedelta(days=1)
        if is_working_day(current, holidays):
            counted += 1
    return current


def working_days_between(
    start: datetime.date, end: datetime.date, holidays: typing.AbstractSet[datetime.date]
) -> int:
    """LIB-COM-10: number of working days x with start < x <= end; 0 if end <= start."""
    count = 0
    current = start
    while current < end:
        current += datetime.timedelta(days=1)
        if is_working_day(current, holidays):
            count += 1
    return count
