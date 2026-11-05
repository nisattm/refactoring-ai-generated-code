"""Clocks (LIB-IF-07 to LIB-IF-09) and the local time zone (LIB-COM-01)."""

import datetime
import typing

# Türkiye: fixed UTC+03:00, no daylight saving time (LIB-COM-01).
LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=3))


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime: ...  # timezone-aware


class SystemClock:
    """The only place that reads the system clock (LIB-TECH-09)."""

    def now(self) -> datetime.datetime:
        return datetime.datetime.now(LOCAL_TZ)


class FixedClock:
    def __init__(self, now: datetime.datetime) -> None:
        self._now = _require_aware(now)

    def now(self) -> datetime.datetime:
        return self._now

    def set(self, now: datetime.datetime) -> None:
        self._now = _require_aware(now)

    def advance(self, *, days: int = 0, hours: int = 0, minutes: int = 0) -> None:
        self._now = self._now + datetime.timedelta(days=days, hours=hours, minutes=minutes)


def _require_aware(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock values must be timezone-aware datetimes")
    return value


def today(clock: Clock) -> datetime.date:
    """'Today' is the local date of the clock (LIB-COM-02)."""
    return clock.now().astimezone(LOCAL_TZ).date()
