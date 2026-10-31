"""Calendar endpoints (LIB-CORE-01 to LIB-CORE-06)."""
import datetime
import re

from fastapi import APIRouter, Query, Request

from ..core import calendar as cal
from ..core.errors import ValidationFailed
from ..core.holidays import HOLIDAY_NAMES

router = APIRouter(prefix="/api/v1/calendar")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INT_RE = re.compile(r"^[+-]?\d+$")


def _date(name: str, raw: str | None, fields: list) -> datetime.date | None:
    if raw is None:
        fields.append({"field": name, "problem": "is required"})
        return None
    try:
        if not _DATE_RE.match(raw):
            raise ValueError
        return datetime.date.fromisoformat(raw)
    except ValueError:
        fields.append({"field": name, "problem": "must be a date in YYYY-MM-DD format"})
        return None


def _int(name: str, raw: str | None, lo: int, hi: int, fields: list) -> int | None:
    if raw is None:
        fields.append({"field": name, "problem": "is required"})
        return None
    if not _INT_RE.match(raw.strip()):
        fields.append({"field": name, "problem": "must be an integer"})
        return None
    v = int(raw)
    if not lo <= v <= hi:
        fields.append({"field": name, "problem": f"must be between {lo} and {hi}"})
        return None
    return v


def _fail(fields: list) -> None:
    if fields:
        raise ValidationFailed(fields)


def _holidays(request: Request):
    return request.app.state.settings.holidays


@router.get("/holidays")
def holidays(request: Request, year: str | None = Query(None)):
    fields: list = []
    y = _int("year", year, 1900, 2100, fields)
    _fail(fields)
    items = [
        {"date": d.isoformat(), "name": HOLIDAY_NAMES.get(d, "Holiday")}
        for d in sorted(_holidays(request))
        if d.year == y
    ]
    return {"year": y, "holidays": items}


@router.get("/days/{date}")
def day(request: Request, date: str):
    fields: list = []
    d = _date("date", date, fields)
    _fail(fields)
    reason = cal.day_reason(d, _holidays(request))
    return {"date": d.isoformat(), "working_day": reason is None, "reason": reason}


@router.get("/next-working-day")
def next_working_day(request: Request, date: str | None = Query(None)):
    fields: list = []
    d = _date("date", date, fields)
    _fail(fields)
    return {"date": cal.next_working_day(d, _holidays(request)).isoformat()}


@router.get("/add-working-days")
def add_working_days(request: Request, date: str | None = Query(None), days: str | None = Query(None)):
    fields: list = []
    d = _date("date", date, fields)
    n = _int("days", days, 1, 365, fields)
    _fail(fields)
    try:
        result = cal.add_working_days(d, n, _holidays(request))
    except OverflowError:
        raise ValidationFailed([{"field": "date", "problem": "date out of range"}])
    return {"date": result.isoformat()}


@router.get("/working-days-between")
def working_days_between(request: Request, start: str | None = Query(None), end: str | None = Query(None)):
    fields: list = []
    s = _date("start", start, fields)
    e = _date("end", end, fields)
    _fail(fields)
    if (e - s).days > 3660:
        raise ValidationFailed([{"field": "end", "problem": "range must not exceed 3660 days"}])
    return {"working_days": cal.working_days_between(s, e, _holidays(request))}
