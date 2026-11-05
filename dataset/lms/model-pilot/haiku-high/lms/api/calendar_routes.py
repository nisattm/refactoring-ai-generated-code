"""Module 1 endpoints: the working-day calendar (section 5.1). Public, no authentication."""

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from lms.api.deps import get_settings
from lms.core.errors import field_problem, validation_error
from lms.core.request_types import IsoDate
from lms.core.settings import Settings
from lms.core.workdays import (
    HOLIDAY_NAMES,
    MAX_BETWEEN_DAYS,
    add_working_days,
    day_reason,
    is_working_day,
    next_working_day,
    working_days_between,
)

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/holidays")
def list_holidays(
    settings: SettingsDep,
    year: Annotated[int, Query(ge=1900, le=2100)],
) -> dict:
    holidays = sorted(day for day in settings.holidays if day.year == year)
    return {
        "year": year,
        "holidays": [
            {"date": day.isoformat(), "name": HOLIDAY_NAMES.get(day)} for day in holidays
        ],
    }


@router.get("/days/{date}")
def get_day(date: IsoDate, settings: SettingsDep) -> dict:
    return {
        "date": date.isoformat(),
        "working_day": is_working_day(date, settings.holidays),
        "reason": day_reason(date, settings.holidays),
    }


@router.get("/next-working-day")
def get_next_working_day(date: IsoDate, settings: SettingsDep) -> dict:
    return {"date": next_working_day(date, settings.holidays).isoformat()}


@router.get("/add-working-days")
def get_add_working_days(
    date: IsoDate,
    settings: SettingsDep,
    days: Annotated[int, Query(ge=1, le=365)],
) -> dict:
    return {"date": add_working_days(date, days, settings.holidays).isoformat()}


@router.get("/working-days-between")
def get_working_days_between(
    start: IsoDate,
    end: IsoDate,
    settings: SettingsDep,
) -> dict:
    if end > start and (end - start) > datetime.timedelta(days=MAX_BETWEEN_DAYS):
        raise validation_error(
            field_problem("end", f"must be at most {MAX_BETWEEN_DAYS} days after start")
        )
    return {"working_days": working_days_between(start, end, settings.holidays)}
