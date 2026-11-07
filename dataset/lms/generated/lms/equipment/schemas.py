"""Request and response schemas of module 16 (section 24)."""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, StrictBool, StrictInt, field_validator

from lms.core.clock import LOCAL_TZ
from lms.core.money import Money, format_amount
from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime, parse_date, parse_datetime
from lms.equipment.models import (
    EquipmentItem,
    EquipmentLoan,
    EquipmentReservation,
    EquipmentTraining,
    EquipmentType,
)

PeriodUnit = Literal["hours", "working_days"]
ItemStatus = Literal["available", "on_loan", "in_repair", "lost", "retired"]
LoanStatus = Literal["open", "returned", "lost"]
ReservationStatus = Literal["booked", "collected", "cancelled", "expired"]
Condition = Literal["good", "damaged"]

_TYPE_CODE_RE = re.compile(r"^[A-Z0-9_]{2,20}$")
_ASSET_TAG_RE = re.compile(r"^[A-Z0-9-]{4,20}$")

Id = StrictInt
Name = Annotated[str, Field(min_length=1, max_length=200)]
SerialNo = Annotated[str, Field(min_length=1, max_length=50)]

MIN_LATE_FEE = Decimal("0.50")
MAX_LATE_FEE = Decimal("50.00")
MIN_VALUE = Decimal("1.00")
MAX_VALUE = Decimal("100000.00")


def _parse_date_value(value: Any) -> datetime.date:
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value
    return parse_date(value)


DateValue = Annotated[datetime.date, BeforeValidator(_parse_date_value)]


def _parse_starts_at(value: Any) -> datetime.datetime:
    """A date-time with a UTC offset (LIB-COM-04), in local time at minutes ``00`` or ``30`` and seconds 0."""
    parsed = value if isinstance(value, datetime.datetime) and value.tzinfo is not None else parse_datetime(value)
    local = parsed.astimezone(LOCAL_TZ)
    if local.minute not in (0, 30) or local.second != 0 or local.microsecond != 0:
        raise ValueError("starts_at must be at minutes 00 or 30 with seconds 0")
    return local


StartsAt = Annotated[datetime.datetime, BeforeValidator(_parse_starts_at)]


def _upper_code(value: str) -> str:
    return value.upper()


def type_range_problems(
    period_unit: str | None, period: int | None, hourly_late_fee: Decimal | None, max_open: int | None
) -> list[dict[str, str]]:
    """The value rules of 24.2 for equipment types; ``None`` skips a field. Without a unit, the widest range applies."""
    problems: list[dict[str, str]] = []
    if period is not None:
        upper = 8 if period_unit == "hours" else 10
        if not 1 <= period <= upper:
            where = "hours" if period_unit == "hours" else "working_days"
            problems.append({"field": "period", "problem": f"period must be 1-{upper}" + (f" for {where}" if period_unit else "")})
    if hourly_late_fee is not None and not MIN_LATE_FEE <= hourly_late_fee <= MAX_LATE_FEE:
        problems.append({"field": "hourly_late_fee", "problem": "hourly_late_fee must be between 0.50 and 50.00"})
    if max_open is not None and not 1 <= max_open <= 3:
        problems.append({"field": "max_open_per_member", "problem": "max_open_per_member must be 1-3"})
    return problems


class TypeCreateIn(RequestModel):
    code: str
    name: Name
    period_unit: PeriodUnit
    period: Id
    hourly_late_fee: Money
    requires_training: StrictBool = False
    max_open_per_member: Id

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = _upper_code(value)
        if not _TYPE_CODE_RE.match(value):
            raise ValueError("code must be 2-20 characters from A-Z, 0-9 and _")
        return value


class TypePatchIn(RequestModel):
    """Any subset of the fields; ``null`` is not accepted for any of them."""

    name: Name = None  # type: ignore[assignment]
    period: Id = None  # type: ignore[assignment]
    hourly_late_fee: Money = None  # type: ignore[assignment]
    requires_training: StrictBool = None  # type: ignore[assignment]
    max_open_per_member: Id = None  # type: ignore[assignment]
    is_active: StrictBool = None  # type: ignore[assignment]


class TypeOut(BaseModel):
    id: int
    code: str
    name: str
    period_unit: str
    period: int
    hourly_late_fee: str
    requires_training: bool
    max_open_per_member: int
    is_active: bool
    items_total: int
    items_available: int


def type_out(t: EquipmentType, items_total: int = 0, items_available: int = 0) -> TypeOut:
    return TypeOut(
        id=t.id,
        code=t.code,
        name=t.name,
        period_unit=t.period_unit,
        period=t.period,
        hourly_late_fee=format_amount(t.hourly_late_fee),
        requires_training=t.requires_training,
        max_open_per_member=t.max_open_per_member,
        is_active=t.is_active,
        items_total=items_total,
        items_available=items_available,
    )


class ItemCreateIn(RequestModel):
    type_id: Id
    asset_tag: str
    serial_no: SerialNo
    branch_id: Id
    value: Money
    acquired_on: DateValue

    @field_validator("asset_tag")
    @classmethod
    def _tag(cls, value: str) -> str:
        value = _upper_code(value)
        if not _ASSET_TAG_RE.match(value):
            raise ValueError("asset_tag must be 4-20 characters from A-Z, 0-9 and -")
        return value

    @field_validator("value")
    @classmethod
    def _value(cls, value: Decimal) -> Decimal:
        if not MIN_VALUE <= value <= MAX_VALUE:
            raise ValueError("value must be between 1.00 and 100000.00")
        return value


class ItemPatchIn(RequestModel):
    serial_no: SerialNo = None  # type: ignore[assignment]
    value: Money = None  # type: ignore[assignment]
    branch_id: Id = None  # type: ignore[assignment]

    @field_validator("value")
    @classmethod
    def _value(cls, value: Decimal) -> Decimal:
        if not MIN_VALUE <= value <= MAX_VALUE:
            raise ValueError("value must be between 1.00 and 100000.00")
        return value


class ItemOut(BaseModel):
    id: int
    type_id: int
    asset_tag: str
    serial_no: str
    branch_id: int
    value: str
    status: str
    acquired_on: str
    created_at: str


def item_out(item: EquipmentItem) -> ItemOut:
    return ItemOut(
        id=item.id,
        type_id=item.type_id,
        asset_tag=item.asset_tag,
        serial_no=item.serial_no,
        branch_id=item.branch_id,
        value=format_amount(item.value),
        status=item.status,
        acquired_on=item.acquired_on.isoformat(),
        created_at=format_datetime(item.created_at),
    )


class TrainingIn(RequestModel):
    type_id: Id
    completed_on: DateValue


class TrainingOut(BaseModel):
    id: int
    member_id: int
    type_id: int
    completed_on: str
    valid_until: str
    recorded_by: int
    created_at: str


def training_out(t: EquipmentTraining) -> TrainingOut:
    return TrainingOut(
        id=t.id,
        member_id=t.member_id,
        type_id=t.type_id,
        completed_on=t.completed_on.isoformat(),
        valid_until=t.valid_until.isoformat(),
        recorded_by=t.recorded_by,
        created_at=format_datetime(t.created_at),
    )


class LoanCreateIn(RequestModel):
    member_id: Id
    item_id: Id | None = None
    reservation_id: Id | None = None


class ReturnIn(RequestModel):
    condition: Condition
    damage_fee: Money | None = None


class EquipmentLoanOut(BaseModel):
    id: int
    item_id: int
    member_id: int
    branch_id: int
    reservation_id: int | None
    loaned_at: str
    due_at: str
    extended: bool
    status: str
    returned_at: str | None
    return_condition: str | None
    late_hours: int | None
    lent_by: int | None
    received_by: int | None
    asset_tag: str
    type_id: int
    type_code: str
    overdue: bool
    accrued_late_fee: str


def loan_out(
    loan: EquipmentLoan, asset_tag: str, type_code: str, now: datetime.datetime, accrued: Decimal
) -> EquipmentLoanOut:
    return EquipmentLoanOut(
        id=loan.id,
        item_id=loan.item_id,
        member_id=loan.member_id,
        branch_id=loan.branch_id,
        reservation_id=loan.reservation_id,
        loaned_at=format_datetime(loan.loaned_at),
        due_at=format_datetime(loan.due_at),
        extended=loan.extended,
        status=loan.status,
        returned_at=format_datetime(loan.returned_at) if loan.returned_at is not None else None,
        return_condition=loan.return_condition,
        late_hours=loan.late_hours,
        lent_by=loan.lent_by,
        received_by=loan.received_by,
        asset_tag=asset_tag,
        type_id=loan.type_id,
        type_code=type_code,
        overdue=loan.status == "open" and now > loan.due_at + datetime.timedelta(minutes=15),
        accrued_late_fee=format_amount(accrued),
    )


class ReservationCreateIn(RequestModel):
    type_id: Id
    branch_id: Id
    member_id: Id | None = None
    starts_at: StartsAt


class ReservationOut(BaseModel):
    id: int
    type_id: int
    branch_id: int
    member_id: int
    starts_at: str
    ends_at: str
    status: str
    loan_id: int | None
    created_at: str
    closed_at: str | None
    cancel_reason: str | None


def reservation_out(r: EquipmentReservation) -> ReservationOut:
    return ReservationOut(
        id=r.id,
        type_id=r.type_id,
        branch_id=r.branch_id,
        member_id=r.member_id,
        starts_at=format_datetime(r.starts_at),
        ends_at=format_datetime(r.ends_at),
        status=r.status,
        loan_id=r.loan_id,
        created_at=format_datetime(r.created_at),
        closed_at=format_datetime(r.closed_at) if r.closed_at is not None else None,
        cancel_reason=r.cancel_reason,
    )


class SlotOut(BaseModel):
    start: str
    free: int


class AvailabilityOut(BaseModel):
    type_id: int
    branch_id: int
    date: str
    capacity: int
    slots: list[SlotOut]


class ProcessOut(BaseModel):
    expired_reservations: int
    overdue_notices: int


class EquipmentSummaryOut(BaseModel):
    open_loans: int
    overdue_loans: int
    booked_reservations: int


class EquipmentUsageOut(BaseModel):
    type_id: int
    type_code: str
    loans: int
    late_returns: int
    late_hours: int
    damaged_returns: int
    lost: int
    reservations: int
    expired_reservations: int
    fees_created: str
