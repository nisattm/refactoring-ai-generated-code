"""Request and response schemas of module 28 (section 36)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictBool, StrictInt, field_validator

from lms.access.models import AccessBan, Card, DayPass, Visit
from lms.access.rules import MAX_CAPACITY, MAX_DAY_PASS_PRICE
from lms.core.money import ZERO, Money, format_amount
from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime
from lms.rooms.schemas import DateValue

ReportReason = Literal["lost", "damaged"]
Direction = Literal["in", "out"]
PassStatus = Literal["unused", "used", "cancelled"]


# --- requests --------------------------------------------------------------------------------


class ReportIn(RequestModel):
    reason: ReportReason


class SettingsIn(RequestModel):
    """Any subset of the fields (LIB-ACC-10)."""

    capacity: Annotated[StrictInt, Field(ge=1, le=MAX_CAPACITY)] | None = None
    guest_entry: StrictBool = None  # type: ignore[assignment]
    day_passes: StrictBool = None  # type: ignore[assignment]
    day_pass_price: Money = None  # type: ignore[assignment]

    @field_validator("guest_entry", "day_passes", "day_pass_price", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("this field cannot be null")
        return value

    @field_validator("day_pass_price")
    @classmethod
    def _price(cls, value: Decimal) -> Decimal:
        if not ZERO <= value <= MAX_DAY_PASS_PRICE:
            raise ValueError("day_pass_price must be between 0.00 and 100.00")
        return value


class ScanIn(RequestModel):
    branch_id: StrictInt
    direction: Direction
    card_no: str | None = None
    pass_code: str | None = None


class DayPassIn(RequestModel):
    branch_id: StrictInt
    visitor_name: Annotated[str, Field(min_length=1, max_length=200)]


class BanIn(RequestModel):
    reason: Annotated[str, Field(min_length=1, max_length=200)]
    starts_on: DateValue | None = None
    ends_on: DateValue


# --- responses -------------------------------------------------------------------------------


class CardOut(BaseModel):
    id: int
    card_no: str
    member_id: int
    status: str
    issued_on: str
    expires_on: str
    replaces_id: int | None
    fee_id: int | None
    ended_on: str | None


class CardMemberOut(BaseModel):
    id: int
    member_no: str
    full_name: str
    membership_type: str
    status: str


class CardDetailOut(CardOut):
    member: CardMemberOut


def card_out(card: Card) -> CardOut:
    return CardOut(
        id=card.id,
        card_no=card.card_no,
        member_id=card.member_id,
        status=card.status,
        issued_on=card.issued_on.isoformat(),
        expires_on=card.expires_on.isoformat(),
        replaces_id=card.replaces_id,
        fee_id=card.fee_id,
        ended_on=card.ended_on.isoformat() if card.ended_on is not None else None,
    )


class SettingsOut(BaseModel):
    branch_id: int
    capacity: int | None
    guest_entry: bool
    day_passes: bool
    day_pass_price: str


class OccupancyOut(BaseModel):
    branch_id: int
    inside: int
    members: int
    visitors: int
    capacity: int | None
    free: int | None


class InsideOut(BaseModel):
    visit_id: int
    member_id: int | None
    full_name: str | None
    day_pass_code: str | None
    entered_at: str


class ScanOut(BaseModel):
    result: str
    visit_id: int
    member_id: int | None
    day_pass_id: int | None


class VisitOut(BaseModel):
    id: int
    branch_id: int
    member_id: int | None
    day_pass_id: int | None
    card_id: int | None
    entered_at: str
    left_at: str | None
    closed_by: str | None
    minutes: int | None


def visit_out(visit: Visit) -> VisitOut:
    return VisitOut(
        id=visit.id,
        branch_id=visit.branch_id,
        member_id=visit.member_id,
        day_pass_id=visit.day_pass_id,
        card_id=visit.card_id,
        entered_at=format_datetime(visit.entered_at),
        left_at=format_datetime(visit.left_at) if visit.left_at is not None else None,
        closed_by=visit.closed_by,
        minutes=visit.minutes,
    )


class AlertOut(BaseModel):
    card_no: str
    branch_id: int
    at: str


class DayPassOut(BaseModel):
    id: int
    code: str
    branch_id: int
    visitor_name: str
    valid_on: str
    price: str
    status: str
    sold_at: str
    sold_by: int


def day_pass_out(day_pass: DayPass) -> DayPassOut:
    return DayPassOut(
        id=day_pass.id,
        code=day_pass.code,
        branch_id=day_pass.branch_id,
        visitor_name=day_pass.visitor_name,
        valid_on=day_pass.valid_on.isoformat(),
        price=format_amount(day_pass.price),
        status=day_pass.status,
        sold_at=format_datetime(day_pass.sold_at),
        sold_by=day_pass.sold_by,
    )


class BanOut(BaseModel):
    id: int
    member_id: int
    reason: str
    starts_on: str
    ends_on: str
    lifted_at: str | None
    created_by: int
    in_force: bool


def ban_out(ban: AccessBan, today: datetime.date) -> BanOut:
    return BanOut(
        id=ban.id,
        member_id=ban.member_id,
        reason=ban.reason,
        starts_on=ban.starts_on.isoformat(),
        ends_on=ban.ends_on.isoformat(),
        lifted_at=format_datetime(ban.lifted_at) if ban.lifted_at is not None else None,
        created_by=ban.created_by,
        in_force=ban.in_force_on(today),
    )


class ProcessOut(BaseModel):
    visits_closed: int
    cards_expired: int
    passes_expired: int


class VisitsReportOut(BaseModel):
    branch_id: int
    visits: int
    member_visits: int
    unique_members: int
    pass_visits: int
    average_minutes: str | None
    peak_occupancy: int
    pass_revenue: str
    denied: int


class AccessSummaryOut(BaseModel):
    card_no: str | None
    card_status: str | None
    inside_branch_id: int | None
    visits_this_month: int
