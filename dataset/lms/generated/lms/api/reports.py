"""Report endpoints (section 16). Only for librarians and admins."""

from __future__ import annotations

import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response

from lms.auth.deps import StaffOnly
from lms.core.clock import today as clock_today
from lms.core.db import SessionDep
from lms.core.errors import ValidationFailed
from lms.core.money import format_amount
from lms.core.pagination import Page, PageDep, paginate_sequence
from lms.core.timeutil import parse_date
from lms.reports import service
from lms.digital import usage as digital_usage
from lms.digital.schemas import DigitalUsageOut, ResourceKind
from lms.equipment import usage as equipment_usage
from lms.ill import usage as ill_usage
from lms.ill.schemas import IllActivityOut
from lms.equipment.schemas import EquipmentUsageOut
from lms.rooms import usage as room_usage
from lms.rooms.schemas import RoomKind, RoomUsageOut
from lms.reports.schemas import (
    InventoryOut,
    MonthlySummaryOut,
    MostBorrowedOut,
    OverdueItemOut,
    OverduePage,
)

router = APIRouter(prefix="/reports", tags=["reports"])

MAX_SPAN_DAYS = 365
CSV_TYPE = "text/csv; charset=utf-8"
MOST_BORROWED_COLUMNS = ("rank", "book_id", "title", "isbn", "loan_count")
OVERDUE_COLUMNS = tuple(OverdueItemOut.model_fields)

Format = Literal["json", "csv"]


def _csv_response(columns: tuple[str, ...], items: list) -> Response:
    text = service.to_csv(columns, (item.model_dump() for item in items))
    return Response(content=text.encode("utf-8"), media_type=CSV_TYPE)


def _required_date(name: str, raw: str | None, problems: list[dict[str, str]]) -> datetime.date | None:
    if raw is None:
        problems.append({"field": name, "problem": "field required"})
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        problems.append({"field": name, "problem": "expected a valid date in the form YYYY-MM-DD"})
        return None


@router.get("/most-borrowed", response_model=MostBorrowedOut, response_model_by_alias=True)
def most_borrowed(
    db: SessionDep,
    _: StaffOnly,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    format: Annotated[Format, Query()] = "json",
):
    problems: list[dict[str, str]] = []
    start = _required_date("from", first, problems)
    end = _required_date("to", to, problems)
    if problems:
        raise ValidationFailed(problems)
    assert start is not None and end is not None
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days > MAX_SPAN_DAYS:
        raise ValidationFailed.single("to", "the range must not be longer than 366 days including both ends")
    items = service.most_borrowed(db, start, end, branch_id, limit)
    if format == "csv":
        return _csv_response(MOST_BORROWED_COLUMNS, items)
    return MostBorrowedOut(**{"from": start.isoformat()}, to=end.isoformat(), branch_id=branch_id, items=items)


@router.get("/overdue", response_model=OverduePage)
def overdue(
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    branch_id: Annotated[int | None, Query()] = None,
    format: Annotated[Format, Query()] = "json",
):
    settings = request.app.state.settings
    day = clock_today(settings.clock)
    if format == "csv":
        return _csv_response(OVERDUE_COLUMNS, service.overdue_items(db, day, settings.holidays, branch_id, None))
    total, total_accrued = service.overdue_total(db, day, settings.holidays, branch_id)
    items = service.overdue_items(db, day, settings.holidays, branch_id, page)
    return OverduePage(
        items=items,
        page=page.page,
        page_size=page.page_size,
        total=total,
        total_accrued=format_amount(total_accrued),
    )


@router.get("/monthly-summary", response_model=MonthlySummaryOut)
def monthly_summary(
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    year: Annotated[int, Query(ge=1900, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
    branch_id: Annotated[int | None, Query()] = None,
) -> MonthlySummaryOut:
    day = clock_today(request.app.state.settings.clock)
    if (year, month) > (day.year, day.month):
        raise ValidationFailed.single("month", "the month must not be after the current month")
    return service.monthly_summary(db, year, month, branch_id)


@router.get("/inventory", response_model=InventoryOut)
def inventory(db: SessionDep, _: StaffOnly, branch_id: Annotated[int | None, Query()] = None) -> InventoryOut:
    return InventoryOut(items=service.inventory(db, branch_id))


@router.get("/room-usage", response_model=Page[RoomUsageOut])
def room_usage_report(
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    kind: Annotated[RoomKind | None, Query()] = None,
) -> Page[RoomUsageOut]:
    problems: list[dict[str, str]] = []
    start = _required_date("from", first, problems)
    end = _required_date("to", to, problems)
    if problems:
        raise ValidationFailed(problems)
    assert start is not None and end is not None
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days > 365:
        raise ValidationFailed.single("to", "the range must not be longer than 366 days including both ends")
    items = room_usage.room_usage(db, start, end, request.app.state.settings.holidays, branch_id=branch_id, kind=kind)
    return paginate_sequence(items, page)


@router.get("/equipment-usage", response_model=Page[EquipmentUsageOut])
def equipment_usage_report(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
) -> Page[EquipmentUsageOut]:
    problems: list[dict[str, str]] = []
    start = _required_date("from", first, problems)
    end = _required_date("to", to, problems)
    if problems:
        raise ValidationFailed(problems)
    assert start is not None and end is not None
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days > 365:
        raise ValidationFailed.single("to", "the range must not be longer than 366 days including both ends")
    return paginate_sequence(equipment_usage.equipment_usage(db, start, end, branch_id=branch_id), page)


@router.get("/digital-usage", response_model=Page[DigitalUsageOut])
def digital_usage_report(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    kind: Annotated[ResourceKind | None, Query()] = None,
) -> Page[DigitalUsageOut]:
    problems: list[dict[str, str]] = []
    start = _required_date("from", first, problems)
    end = _required_date("to", to, problems)
    if problems:
        raise ValidationFailed(problems)
    assert start is not None and end is not None
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days > 365:
        raise ValidationFailed.single("to", "the range must not be longer than 366 days including both ends")
    return paginate_sequence(digital_usage.digital_usage(db, start, end, kind=kind), page)


@router.get("/ill-activity", response_model=Page[IllActivityOut])
def ill_activity_report(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> Page[IllActivityOut]:
    problems: list[dict[str, str]] = []
    start = _required_date("from", first, problems)
    end = _required_date("to", to, problems)
    if problems:
        raise ValidationFailed(problems)
    assert start is not None and end is not None
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days > 365:
        raise ValidationFailed.single("to", "the range must not be longer than 366 days including both ends")
    return paginate_sequence(ill_usage.ill_activity(db, start, end), page)
