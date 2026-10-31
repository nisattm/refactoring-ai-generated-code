"""Clock abstraction (LIB-IF-07 to LIB-IF-09). The only place that reads the system clock."""

from __future__ import annotations

import datetime
import typing

LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=3), "+03:00")


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime: ...  # timezone-aware


class SystemClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(LOCAL_TZ)


def _require_aware(value: datetime.datetime) -> datetime.datetime:
    if not isinstance(value, datetime.datetime):
        raise ValueError("now must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value


class FixedClock:
    def __init__(self, now: datetime.datetime) -> None:
        self._now = _require_aware(now)

    def now(self) -> datetime.datetime:
        return self._now

    def set(self, now: datetime.datetime) -> None:
        self._now = _require_aware(now)

    def advance(self, *, days: int = 0, hours: int = 0, minutes: int = 0) -> None:
        self._now = self._now + datetime.timedelta(days=days, hours=hours, minutes=minutes)


def local_now(clock: Clock) -> datetime.datetime:
    """Current time of ``clock`` in local time (UTC+03:00)."""
    return clock.now().astimezone(LOCAL_TZ)


def today(clock: Clock) -> datetime.date:
    """LIB-COM-02: the local date of the clock."""
    return local_now(clock).date()
