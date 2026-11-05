"""Module 1 endpoints: the public working-day calendar (section 5.1)."""

import datetime
import re

from fastapi import APIRouter, Depends, Path, Query, Request

from lms.api.errors import validation_error
from lms.core.settings import HOLIDAY_NAMES, UNNAMED_HOLIDAY, Settings
from lms.core.working_days import (
    add_working_days,
    is_holiday,
    is_weekend,
    next_working_day_on_or_after,
    working_days_between,
)

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])

_DATE_FORMAT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_MAX_SPAN_DAYS = 3660
_MAX_ADD_DAYS = 365


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def parse_date(value: str, field: str) -> datetime.date:
    """Parse a strict YYYY-MM-DD date (LIB-COM-04)."""
    if not _DATE_FORMAT.fullmatch(value):
        raise validation_error(field, "must be a date in the form YYYY-MM-DD")
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise validation_error(field, "is not a valid calendar date") from None


@router.get("/holidays")
def list_holidays(
    year: int = Query(ge=1900, le=2100),
    settings: Settings = Depends(get_settings),
) -> dict:
    days = sorted(day for day in settings.holidays if day.year == year)
    return {
        "year": year,
        "holidays": [
            {"date": day.isoformat(), "name": HOLIDAY_NAMES.get(day, UNNAMED_HOLIDAY)}
            for day in days
        ],
    }


@router.get("/days/{date}")
def check_day(
    day_text: str = Path(alias="date"),
    settings: Settings = Depends(get_settings),
) -> dict:
    day = parse_date(day_text, "date")
    if is_holiday(day, settings):
        reason = "holiday"
    elif is_weekend(day):
        reason = "weekend"
    else:
        reason = None
    return {"date": day.isoformat(), "working_day": reason is None, "reason": reason}


@router.get("/next-working-day")
def next_working_day(
    date_text: str = Query(alias="date"),
    settings: Settings = Depends(get_settings),
) -> dict:
    day = parse_date(date_text, "date")
    try:
        result = next_working_day_on_or_after(day, settings)
    except OverflowError:
        raise validation_error("date", "is too far in the future") from None
    return {"date": result.isoformat()}


@router.get("/add-working-days")
def add_days(
    date_text: str = Query(alias="date"),
    days: int = Query(ge=1, le=_MAX_ADD_DAYS),
    settings: Settings = Depends(get_settings),
) -> dict:
    day = parse_date(date_text, "date")
    try:
        result = add_working_days(day, days, settings)
    except OverflowError:
        raise validation_error("date", "is too far in the future") from None
    return {"date": result.isoformat()}


@router.get("/working-days-between")
def count_working_days(
    start: str = Query(),
    end: str = Query(),
    settings: Settings = Depends(get_settings),
) -> dict:
    start_day = parse_date(start, "start")
    end_day = parse_date(end, "end")
    if (end_day - start_day).days > _MAX_SPAN_DAYS:
        raise validation_error("end", "is more than 3660 days after start")
    return {"working_days": working_days_between(start_day, end_day, settings)}
