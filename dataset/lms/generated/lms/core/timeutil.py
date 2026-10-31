"""Date-time storage and (de)serialization (LIB-COM-03, LIB-COM-04)."""

from __future__ import annotations

import datetime
import re
from typing import Any

import sqlalchemy as sa

from lms.core.clock import LOCAL_TZ

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(text: str) -> datetime.date:
    """Strict ``YYYY-MM-DD``; raises ``ValueError``."""
    if not isinstance(text, str) or not _DATE_RE.match(text):
        raise ValueError("expected a date in the form YYYY-MM-DD")
    return datetime.date.fromisoformat(text)


def parse_datetime(text: str) -> datetime.datetime:
    """ISO 8601 date-time with a UTC offset; raises ``ValueError`` for a naive value."""
    if not isinstance(text, str):
        raise ValueError("expected an ISO 8601 date-time with offset")
    value = datetime.datetime.fromisoformat(text.strip())
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("date-time must include a UTC offset")
    return value


def format_datetime(value: datetime.datetime) -> str:
    """Local time (UTC+03:00) as ISO 8601 with offset, e.g. ``2026-11-02T09:30:00+03:00``."""
    return value.astimezone(LOCAL_TZ).isoformat()


class TZDateTime(sa.TypeDecorator[datetime.datetime]):
    """Stores aware date-times as UTC; returns them aware, in local time."""

    impl = sa.DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime.datetime | None, dialect: Any) -> datetime.datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("naive date-time cannot be stored")
        return value.astimezone(datetime.timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime.datetime | None, dialect: Any) -> datetime.datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=datetime.timezone.utc).astimezone(LOCAL_TZ)
