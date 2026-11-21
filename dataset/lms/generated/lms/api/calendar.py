"""Calendar endpoints (section 5.1). Public: no authentication."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from lms.api.common import QueryParams, settings_of
from lms.core import calendar as cal
from lms.core.errors import ValidationFailed
from lms.core.holidays import holiday_name

router = APIRouter(prefix="/calendar", tags=["calendar"])

MAX_SPAN_DAYS = 3660


class HolidayOut(BaseModel):
    date: str
    name: str


class HolidaysOut(BaseModel):
    year: int
    holidays: list[HolidayOut]


class DayOut(BaseModel):
    date: str
    working_day: bool
    reason: str | None


class DateOut(BaseModel):
    date: str


class WorkingDaysOut(BaseModel):
    working_days: int


def _overflow() -> ValidationFailed:
    return ValidationFailed.single("date", "date is outside the supported range")


@router.get("/holidays", response_model=HolidaysOut)
def holidays(request: Request, year: Annotated[str | None, Query()] = None) -> HolidaysOut:
    p = QueryParams()
    value = p.integer("year", year, 1900, 2100)
    p.check()
    assert value is not None
    days = sorted(d for d in settings_of(request).holidays if d.year == value)
    return HolidaysOut(year=value, holidays=[HolidayOut(date=d.isoformat(), name=holiday_name(d)) for d in days])


@router.get("/days/{date}", response_model=DayOut)
def day_info(request: Request, date: str) -> DayOut:
    p = QueryParams()
    value = p.date("date", date)
    p.check()
    assert value is not None
    reason = cal.day_reason(value, settings_of(request).holidays)
    return DayOut(date=value.isoformat(), working_day=reason is None, reason=reason)


@router.get("/next-working-day", response_model=DateOut)
def next_working_day(request: Request, date: Annotated[str | None, Query()] = None) -> DateOut:
    p = QueryParams()
    value = p.date("date", date)
    p.check()
    assert value is not None
    try:
        result = cal.next_working_day(value, settings_of(request).holidays)
    except OverflowError:
        raise _overflow() from None
    return DateOut(date=result.isoformat())


@router.get("/add-working-days", response_model=DateOut)
def add_working_days(
    request: Request,
    date: Annotated[str | None, Query()] = None,
    days: Annotated[str | None, Query()] = None,
) -> DateOut:
    p = QueryParams()
    value = p.date("date", date)
    count = p.integer("days", days, 1, 365)
    p.check()
    assert value is not None and count is not None
    try:
        result = cal.add_working_days(value, count, settings_of(request).holidays)
    except OverflowError:
        raise _overflow() from None
    return DateOut(date=result.isoformat())


@router.get("/working-days-between", response_model=WorkingDaysOut)
def working_days_between(
    request: Request,
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
) -> WorkingDaysOut:
    p = QueryParams()
    first = p.date("start", start)
    last = p.date("end", end)
    p.check()
    assert first is not None and last is not None
    if (last - first).days > MAX_SPAN_DAYS:
        raise ValidationFailed.single("end", f"end must be at most {MAX_SPAN_DAYS} days after start")
    return WorkingDaysOut(working_days=cal.working_days_between(first, last, settings_of(request).holidays))
