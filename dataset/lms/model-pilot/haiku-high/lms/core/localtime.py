"""Local time zone and date helpers (LIB-COM-01 to LIB-COM-03)."""

import datetime
import typing

if typing.TYPE_CHECKING:
    from lms.core.clock import Clock

# LIB-COM-01: fixed UTC+03:00, no daylight saving time.
LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=3))


def to_local(value: datetime.datetime) -> datetime.datetime:
    """Convert an aware date-time to local time."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("date-time must be timezone-aware")
    return value.astimezone(LOCAL_TZ)


def today(clock: "Clock") -> datetime.date:
    """LIB-COM-02: the local date of the clock's current time."""
    return to_local(clock.now()).date()


def format_datetime(value: datetime.datetime) -> str:
    """LIB-COM-03: ISO 8601 local date-time with offset, e.g. 2026-11-02T09:30:00+03:00."""
    return to_local(value).isoformat()
