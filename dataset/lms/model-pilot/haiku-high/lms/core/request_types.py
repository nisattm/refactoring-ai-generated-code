"""Validated request types for dates and date-times (LIB-COM-04)."""

import datetime
import re
from typing import Annotated

from pydantic import BeforeValidator

from lms.core.localtime import LOCAL_TZ

_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_iso_date(value: object) -> datetime.date:
    """A date in YYYY-MM-DD form. Anything else raises ValueError (a 422 for the client)."""
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise ValueError("must be a date in YYYY-MM-DD format")
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise ValueError("must be a valid calendar date") from None


def parse_aware_datetime(value: object) -> datetime.datetime:
    """An ISO 8601 date-time that includes a UTC offset. A date-time without an offset is rejected."""
    if not isinstance(value, str):
        raise ValueError("must be an ISO 8601 date-time with UTC offset")
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("must be an ISO 8601 date-time with UTC offset") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("must include a UTC offset")
    return parsed.astimezone(LOCAL_TZ)


IsoDate = Annotated[datetime.date, BeforeValidator(parse_iso_date)]
AwareDateTime = Annotated[datetime.datetime, BeforeValidator(parse_aware_datetime)]
