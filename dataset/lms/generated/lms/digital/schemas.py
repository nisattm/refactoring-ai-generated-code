"""Request and response schemas of module 17 (section 25)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, StrictBool, StrictInt, field_validator

from lms.core.money import Money, format_amount
from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime, parse_date
from lms.digital.models import DigitalHold, DigitalLicense, DigitalLoan, DigitalResource, DigitalSession

ResourceKind = Literal["ebook", "database"]
LicenseModel = Literal["perpetual", "subscription"]
LicenseStatus = Literal["pending", "active", "ended", "cancelled"]
LoanStatus = Literal["open", "returned", "expired"]
HoldStatus = Literal["waiting", "ready", "fulfilled", "cancelled", "expired"]

Id = StrictInt
Title = Annotated[str, Field(min_length=1, max_length=200)]
Provider = Annotated[str, Field(min_length=1, max_length=100)]

MAX_COST = Decimal("1000000.00")


def _parse_date_value(value: Any) -> datetime.date:
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value
    return parse_date(value)


DateValue = Annotated[datetime.date, BeforeValidator(_parse_date_value)]


def _check_loan_days(value: int | None) -> int | None:
    if value is not None and not 1 <= value <= 21:
        raise ValueError("loan_days must be between 1 and 21")
    return value


def _check_cost(value: Decimal) -> Decimal:
    if not Decimal("0.00") <= value <= MAX_COST:
        raise ValueError("cost must be between 0.00 and 1000000.00")
    return value


# --- resources -------------------------------------------------------------------------------


class ResourceCreateIn(RequestModel):
    kind: ResourceKind
    title: Title
    provider: Provider
    book_id: Id | None = None
    loan_days: Id | None = None

    @field_validator("loan_days")
    @classmethod
    def _loan_days(cls, value: int | None) -> int | None:
        return _check_loan_days(value)


class ResourcePatchIn(RequestModel):
    """Any subset of the fields; ``kind`` cannot be changed (unknown field, 422)."""

    title: Title = None  # type: ignore[assignment]
    provider: Provider = None  # type: ignore[assignment]
    book_id: Id | None = None
    loan_days: Id | None = None
    is_active: StrictBool = None  # type: ignore[assignment]

    @field_validator("loan_days")
    @classmethod
    def _loan_days(cls, value: int | None) -> int | None:
        return _check_loan_days(value)


class ResourceOut(BaseModel):
    id: int
    kind: str
    title: str
    provider: str
    book_id: int | None
    loan_days: int | None
    is_active: bool
    created_at: str
    capacity: int
    in_use: int
    available: int
    waiting_holds: int


def resource_out(
    r: DigitalResource, *, capacity: int, in_use: int, available: int, waiting_holds: int
) -> ResourceOut:
    return ResourceOut(
        id=r.id,
        kind=r.kind,
        title=r.title,
        provider=r.provider,
        book_id=r.book_id,
        loan_days=r.loan_days,
        is_active=r.is_active,
        created_at=format_datetime(r.created_at),
        capacity=capacity,
        in_use=in_use,
        available=available,
        waiting_holds=waiting_holds,
    )


class CalendarDayOut(BaseModel):
    date: str
    capacity: int


class CalendarOut(BaseModel):
    resource_id: int
    days: list[CalendarDayOut]


# --- licenses --------------------------------------------------------------------------------


class LicenseCreateIn(RequestModel):
    model: LicenseModel
    copies: Id
    starts_on: DateValue
    ends_on: DateValue | None = None
    cost: Money
    order_id: Id | None = None

    @field_validator("cost")
    @classmethod
    def _cost(cls, value: Decimal) -> Decimal:
        return _check_cost(value)


class LicensePatchIn(RequestModel):
    copies: Id = None  # type: ignore[assignment]
    cost: Money = None  # type: ignore[assignment]
    ends_on: DateValue | None = None

    @field_validator("cost")
    @classmethod
    def _cost(cls, value: Decimal) -> Decimal:
        return _check_cost(value)


class LicenseRenewIn(RequestModel):
    ends_on: DateValue
    cost: Money
    order_id: Id | None = None

    @field_validator("cost")
    @classmethod
    def _cost(cls, value: Decimal) -> Decimal:
        return _check_cost(value)


class LicenseOut(BaseModel):
    id: int
    resource_id: int
    model: str
    copies: int
    starts_on: str
    ends_on: str | None
    cost: str
    order_id: int | None
    cancelled_on: str | None
    status: str


class ExpiringLicenseOut(LicenseOut):
    resource_title: str


def _license_fields(lic: DigitalLicense, today: datetime.date) -> dict[str, Any]:
    return {
        "id": lic.id,
        "resource_id": lic.resource_id,
        "model": lic.model,
        "copies": lic.copies,
        "starts_on": lic.starts_on.isoformat(),
        "ends_on": lic.ends_on.isoformat() if lic.ends_on is not None else None,
        "cost": format_amount(lic.cost),
        "order_id": lic.order_id,
        "cancelled_on": lic.cancelled_on.isoformat() if lic.cancelled_on is not None else None,
        "status": lic.status_on(today),
    }


def license_out(lic: DigitalLicense, today: datetime.date) -> LicenseOut:
    return LicenseOut(**_license_fields(lic, today))


def expiring_license_out(lic: DigitalLicense, today: datetime.date, resource_title: str) -> ExpiringLicenseOut:
    return ExpiringLicenseOut(**_license_fields(lic, today), resource_title=resource_title)


# --- loans, holds, sessions ------------------------------------------------------------------


class ActionCreateIn(RequestModel):
    """Body of the borrow, hold and session requests: a member sends no ``member_id``, staff must."""

    resource_id: Id
    member_id: Id | None = None


class LoanOut(BaseModel):
    id: int
    resource_id: int
    member_id: int
    hold_id: int | None
    borrowed_at: str
    due_at: str
    renewed: bool
    renewed_at: str | None
    status: str
    ended_at: str | None


def _opt(value: datetime.datetime | None) -> str | None:
    return format_datetime(value) if value is not None else None


def loan_out(loan: DigitalLoan, now: datetime.datetime) -> LoanOut:
    return LoanOut(
        id=loan.id,
        resource_id=loan.resource_id,
        member_id=loan.member_id,
        hold_id=loan.hold_id,
        borrowed_at=format_datetime(loan.borrowed_at),
        due_at=format_datetime(loan.due_at),
        renewed=loan.renewed,
        renewed_at=_opt(loan.renewed_at),
        status=loan.effective_status(now),
        ended_at=_opt(loan.effective_ended_at(now)),
    )


class HoldOut(BaseModel):
    id: int
    resource_id: int
    member_id: int
    status: str
    created_at: str
    ready_at: str | None
    ready_until: str | None
    closed_at: str | None
    cancel_reason: str | None
    position: int | None


def hold_out(hold: DigitalHold, position: int | None) -> HoldOut:
    return HoldOut(
        id=hold.id,
        resource_id=hold.resource_id,
        member_id=hold.member_id,
        status=hold.status,
        created_at=format_datetime(hold.created_at),
        ready_at=_opt(hold.ready_at),
        ready_until=_opt(hold.ready_until),
        closed_at=_opt(hold.closed_at),
        cancel_reason=hold.cancel_reason,
        position=position,
    )


class SessionOut(BaseModel):
    id: int
    resource_id: int
    member_id: int
    started_at: str
    expires_at: str
    closed_at: str | None
    open: bool


def session_out(session: DigitalSession, now: datetime.datetime) -> SessionOut:
    return SessionOut(
        id=session.id,
        resource_id=session.resource_id,
        member_id=session.member_id,
        started_at=format_datetime(session.started_at),
        expires_at=format_datetime(session.expires_at),
        closed_at=_opt(session.closed_at),
        open=session.is_open(now),
    )


class ProcessOut(BaseModel):
    expired_loans: int
    expired_holds: int
    holds_ready: int
    due_soon_notices: int


class DigitalSummaryOut(BaseModel):
    open_loans: int
    waiting_holds: int
    ready_holds: int


class DigitalUsageOut(BaseModel):
    resource_id: int
    kind: str
    title: str
    loans: int
    renewals: int
    holds_placed: int
    holds_expired: int
    sessions: int
    license_cost: str
