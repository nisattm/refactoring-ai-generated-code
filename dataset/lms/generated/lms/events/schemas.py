"""Request and response schemas of module 20 (section 28)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, field_validator

from lms.core.money import ZERO, Money, format_amount
from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime
from lms.events.models import Event, EventBan, EventRegistration
from lms.events.rules import MAX_FEE
from lms.rooms.schemas import HHMM, DateValue, format_time

EventKind = Literal["talk", "workshop", "book_club", "tour"]
Audience = Literal["all", "students", "academics"]
EventStatus = Literal["draft", "published", "cancelled", "completed"]
RegistrationStatus = Literal["registered", "waitlisted", "cancelled", "attended", "no_show"]
Id = StrictInt

Title = Annotated[str, Field(min_length=1, max_length=200)]
Description = Annotated[str, Field(max_length=2000)]
Capacity = Annotated[StrictInt, Field(ge=1, le=200)]


def _check_fee(value: Decimal) -> Decimal:
    if not ZERO <= value <= MAX_FEE:
        raise ValueError("fee must be between 0.00 and 200.00")
    return value


# --- requests --------------------------------------------------------------------------------


class _EventFields(RequestModel):
    title: Title
    description: Description = ""
    kind: EventKind
    branch_id: Id
    room_id: Id | None = None
    start_time: HHMM
    end_time: HHMM
    capacity: Capacity
    fee: Money = ZERO
    audience: Audience = "all"
    staff_id: Id

    @field_validator("fee")
    @classmethod
    def _fee(cls, value: Decimal) -> Decimal:
        return _check_fee(value)


class EventCreateIn(_EventFields):
    date: DateValue


class SeriesCreateIn(_EventFields):
    first_date: DateValue
    weeks: Annotated[StrictInt, Field(ge=2, le=12)]


class EventPatchIn(RequestModel):
    """Any subset of the fields; ``kind``, ``branch_id`` and ``audience`` cannot be changed (unknown here, so ``422``)."""

    title: Title | None = None
    description: Description | None = None
    room_id: Id | None = None
    date: DateValue | None = None
    start_time: HHMM | None = None
    end_time: HHMM | None = None
    capacity: Capacity | None = None
    fee: Money | None = None
    staff_id: Id | None = None

    @field_validator("fee")
    @classmethod
    def _fee(cls, value: Decimal | None) -> Decimal | None:
        return None if value is None else _check_fee(value)


class RegistrationCreateIn(RequestModel):
    member_id: Id | None = None


# --- responses -------------------------------------------------------------------------------


class EventOut(BaseModel):
    id: int
    title: str
    description: str
    kind: str
    branch_id: int
    room_id: int | None
    date: datetime.date
    start_time: str
    end_time: str
    capacity: int
    fee: str
    audience: str
    staff_id: int
    series_id: int | None
    status: str
    cancel_reason: str | None
    created_at: str
    published_at: str | None
    registered: int
    waitlisted: int
    free_places: int
    staff_covered: bool


def _dt(value: datetime.datetime | None) -> str | None:
    return None if value is None else format_datetime(value)


def event_out(event: Event, *, registered: int, waitlisted: int, staff_covered: bool) -> EventOut:
    return EventOut(
        id=event.id,
        title=event.title,
        description=event.description,
        kind=event.kind,
        branch_id=event.branch_id,
        room_id=event.room_id,
        date=event.date,
        start_time=format_time(event.start_time),
        end_time=format_time(event.end_time),
        capacity=event.capacity,
        fee=format_amount(event.fee),
        audience=event.audience,
        staff_id=event.staff_id,
        series_id=event.series_id,
        status=event.status,
        cancel_reason=event.cancel_reason,
        created_at=format_datetime(event.created_at),
        published_at=_dt(event.published_at),
        registered=registered,
        waitlisted=waitlisted,
        free_places=max(event.capacity - registered, 0),
        staff_covered=staff_covered,
    )


class RegistrationOut(BaseModel):
    id: int
    event_id: int
    member_id: int
    status: str
    position: int | None
    created_at: str
    promoted_at: str | None
    cancelled_at: str | None
    attended_at: str | None
    late_cancellation: bool
    cancel_reason: str | None
    fee_id: int | None
    event_title: str
    event_date: datetime.date
    start_time: str


def registration_out(reg: EventRegistration, event: Event, position: int | None) -> RegistrationOut:
    return RegistrationOut(
        id=reg.id,
        event_id=reg.event_id,
        member_id=reg.member_id,
        status=reg.status,
        position=position,
        created_at=format_datetime(reg.created_at),
        promoted_at=_dt(reg.promoted_at),
        cancelled_at=_dt(reg.cancelled_at),
        attended_at=_dt(reg.attended_at),
        late_cancellation=reg.late_cancellation,
        cancel_reason=reg.cancel_reason,
        fee_id=reg.fee_id,
        event_title=event.title,
        event_date=event.date,
        start_time=format_time(event.start_time),
    )


class BanOut(BaseModel):
    id: int
    member_id: int
    starts_on: datetime.date
    ends_on: datetime.date
    created_at: str


def ban_out(ban: EventBan) -> BanOut:
    return BanOut(
        id=ban.id,
        member_id=ban.member_id,
        starts_on=ban.starts_on,
        ends_on=ban.ends_on,
        created_at=format_datetime(ban.created_at),
    )


class SkippedOut(BaseModel):
    date: datetime.date
    error_code: str


class SeriesCreatedOut(BaseModel):
    series_id: int
    created: list[int]
    skipped: list[SkippedOut]


class SeriesCancelledOut(BaseModel):
    cancelled: list[int]


class ProcessOut(BaseModel):
    completed_events: int
    no_shows: int
    bans: int
    reminders: int


class EventSummaryOut(BaseModel):
    registered: int
    waitlisted: int
    no_shows_90_days: int
    banned_until: datetime.date | None


class AttendanceOut(BaseModel):
    event_id: int
    title: str
    kind: str
    date: datetime.date
    status: str
    capacity: int
    registered: int
    attended: int
    no_shows: int
    late_cancellations: int
    fees_charged: str
