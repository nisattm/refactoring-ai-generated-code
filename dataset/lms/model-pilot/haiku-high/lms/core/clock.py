"""Clocks (section 4.3). Only SystemClock reads the system clock (LIB-TECH-09)."""

import datetime
import typing

from lms.core.localtime import LOCAL_TZ


def _require_aware(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime: ...  # timezone-aware


class SystemClock:
    def now(self) -> datetime.datetime:
        # LIB-IF-07: current time in local time (UTC+03:00).
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
