"""Clocks and the fixed local time zone (UTC+03:00, no DST)."""
import datetime
import typing

LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=3))


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime: ...


class SystemClock:
    def now(self) -> datetime.datetime:
        # The only place in the system that reads the system clock.
        return datetime.datetime.now(datetime.timezone.utc).astimezone(LOCAL_TZ)


def _check_aware(value: datetime.datetime) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class FixedClock:
    def __init__(self, now: datetime.datetime) -> None:
        self._now = _check_aware(now)

    def now(self) -> datetime.datetime:
        return self._now

    def set(self, now: datetime.datetime) -> None:
        self._now = _check_aware(now)

    def advance(self, *, days: int = 0, hours: int = 0, minutes: int = 0) -> None:
        self._now = self._now + datetime.timedelta(days=days, hours=hours, minutes=minutes)


def today(clock: Clock) -> datetime.date:
    """LIB-COM-02: the local date of the clock."""
    return clock.now().astimezone(LOCAL_TZ).date()


def to_local(value: datetime.datetime) -> datetime.datetime:
    return value.astimezone(LOCAL_TZ)
