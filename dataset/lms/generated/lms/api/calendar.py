"""Calendar endpoints (section 5.1). Public: no authentication."""

from __future__ import annotations

import datetime
import re
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from lms.core import calendar as cal
from lms.core.errors import ValidationFailed
from lms.core.holidays import holiday_name
from lms.core.settings import Settings
from lms.core.timeutil import parse_date

router = APIRouter(prefix="/calendar", tags=["calendar"])

MAX_SPAN_DAYS = 3660
_INT_RE = re.compile(r"^[+-]?\d+$")


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


class _Params:
    """Collects parse problems so that every invalid parameter is reported (LIB-CORE-06)."""

    def __init__(self) -> None:
        self.problems: list[dict[str, str]] = []

    def date(self, name: str, raw: str | None) -> datetime.date | None:
        if raw is None:
            self.problems.append({"field": name, "problem": "field required"})
            return None
        try:
            return parse_date(raw.strip())
        except ValueError:
            self.problems.append({"field": name, "problem": "expected a valid date in the form YYYY-MM-DD"})
            return None

    def integer(self, name: str, raw: str | None, low: int, high: int) -> int | None:
        if raw is None:
            self.problems.append({"field": name, "problem": "field required"})
            return None
        text = raw.strip()
        if not _INT_RE.match(text) or not low <= int(text) <= high:
            self.problems.append({"field": name, "problem": f"expected an integer between {low} and {high}"})
            return None
        return int(text)

    def check(self) -> None:
        if self.problems:
            raise ValidationFailed(self.problems)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _overflow() -> ValidationFailed:
    return ValidationFailed.single("date", "date is outside the supported range")


@router.get("/holidays", response_model=HolidaysOut)
def holidays(request: Request, year: Annotated[str | None, Query()] = None) -> HolidaysOut:
    p = _Params()
    value = p.integer("year", year, 1900, 2100)
    p.check()
    assert value is not None
    days = sorted(d for d in _settings(request).holidays if d.year == value)
    return HolidaysOut(year=value, holidays=[HolidayOut(date=d.isoformat(), name=holiday_name(d)) for d in days])


@router.get("/days/{date}", response_model=DayOut)
def day_info(request: Request, date: str) -> DayOut:
    p = _Params()
    value = p.date("date", date)
    p.check()
    assert value is not None
    reason = cal.day_reason(value, _settings(request).holidays)
    return DayOut(date=value.isoformat(), working_day=reason is None, reason=reason)


@router.get("/next-working-day", response_model=DateOut)
def next_working_day(request: Request, date: Annotated[str | None, Query()] = None) -> DateOut:
    p = _Params()
    value = p.date("date", date)
    p.check()
    assert value is not None
    try:
        result = cal.next_working_day(value, _settings(request).holidays)
    except OverflowError:
        raise _overflow() from None
    return DateOut(date=result.isoformat())


@router.get("/add-working-days", response_model=DateOut)
def add_working_days(
    request: Request,
    date: Annotated[str | None, Query()] = None,
    days: Annotated[str | None, Query()] = None,
) -> DateOut:
    p = _Params()
    value = p.date("date", date)
    count = p.integer("days", days, 1, 365)
    p.check()
    assert value is not None and count is not None
    try:
        result = cal.add_working_days(value, count, _settings(request).holidays)
    except OverflowError:
        raise _overflow() from None
    return DateOut(date=result.isoformat())


@router.get("/working-days-between", response_model=WorkingDaysOut)
def working_days_between(
    request: Request,
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
) -> WorkingDaysOut:
    p = _Params()
    first = p.date("start", start)
    last = p.date("end", end)
    p.check()
    assert first is not None and last is not None
    if (last - first).days > MAX_SPAN_DAYS:
        raise ValidationFailed.single("end", f"end must be at most {MAX_SPAN_DAYS} days after start")
    return WorkingDaysOut(working_days=cal.working_days_between(first, last, _settings(request).holidays))
