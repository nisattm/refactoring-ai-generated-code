"""Request and response schemas of module 15 (section 23)."""

from __future__ import annotations

import datetime
import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    StrictBool,
    StrictInt,
    ValidationInfo,
    field_validator,
)

from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime, parse_date
from lms.rooms.models import Room, RoomBan, RoomBooking

RoomKind = Literal["individual", "group"]
BookingStatus = Literal["booked", "checked_in", "completed", "cancelled", "no_show"]
FEATURES = ("whiteboard", "projector", "power_outlets", "accessible")

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_CODE_RE = re.compile(r"^[A-Z0-9]{2,10}$")


def parse_time(value: Any) -> datetime.time:
    """Strict ``"HH:MM"`` with minutes ``00`` or ``30`` (section 23.1)."""
    if isinstance(value, datetime.time):
        return value
    if not isinstance(value, str):
        raise ValueError('expected a time in the form "HH:MM"')
    match = _TIME_RE.match(value)
    if match is None:
        raise ValueError('expected a time in the form "HH:MM"')
    if match.group(2) not in ("00", "30"):
        raise ValueError("minutes must be 00 or 30")
    return datetime.time(int(match.group(1)), int(match.group(2)))


def parse_date_value(value: Any) -> datetime.date:
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return value
    return parse_date(value)


def format_time(value: datetime.time) -> str:
    return value.strftime("%H:%M")


HHMM = Annotated[datetime.time, BeforeValidator(parse_time)]
DateValue = Annotated[datetime.date, BeforeValidator(parse_date_value)]
Id = StrictInt


def minutes_of(value: datetime.time) -> int:
    return value.hour * 60 + value.minute


def normalize_features(values: list[str]) -> list[str]:
    unknown = [v for v in values if v not in FEATURES]
    if unknown:
        raise ValueError(f"unknown feature {unknown[0]!r}; allowed: {', '.join(FEATURES)}")
    if len(set(values)) != len(values):
        raise ValueError("features must not contain duplicates")
    return [f for f in FEATURES if f in values]


def room_hours_problems(
    opens_at: datetime.time, closes_at: datetime.time
) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    if opens_at < datetime.time(7, 0):
        problems.append({"field": "opens_at", "problem": "opens_at must not be before 07:00"})
    if closes_at > datetime.time(23, 0):
        problems.append({"field": "closes_at", "problem": "closes_at must not be after 23:00"})
    if opens_at >= closes_at:
        problems.append({"field": "closes_at", "problem": "closes_at must be after opens_at"})
    return problems


def room_capacity_problems(kind: str, capacity: int, min_participants: int) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    if kind == "individual":
        if capacity != 1:
            problems.append({"field": "capacity", "problem": "capacity must be 1 for an individual room"})
        if min_participants != 1:
            problems.append({"field": "min_participants", "problem": "min_participants must be 1 for an individual room"})
    else:
        if not 3 <= capacity <= 12:
            problems.append({"field": "capacity", "problem": "capacity must be 3-12 for a group room"})
        if not 2 <= min_participants <= capacity:
            problems.append(
                {"field": "min_participants", "problem": "min_participants must be between 2 and capacity"}
            )
    return problems


RoomName = Annotated[str, Field(min_length=1, max_length=200)]
Features = list[str]


class _FeatureCheck:
    @field_validator("features", check_fields=False)
    @classmethod
    def _features(cls, value: list[str]) -> list[str]:
        return normalize_features(value)


class RoomCreateIn(_FeatureCheck, RequestModel):
    branch_id: Id
    code: str
    name: RoomName
    kind: RoomKind
    capacity: Id | None = None
    min_participants: Id | None = None
    features: Features = Field(default_factory=list)
    opens_at: HHMM
    closes_at: HHMM

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.upper()
        if not _CODE_RE.match(value):
            raise ValueError("code must be 2-10 characters from A-Z and 0-9")
        return value


class RoomPatchIn(_FeatureCheck, RequestModel):
    """Any subset of the fields; ``null`` is not accepted for any of them."""

    name: RoomName = None  # type: ignore[assignment]
    features: Features = None  # type: ignore[assignment]
    capacity: Id = None  # type: ignore[assignment]
    min_participants: Id = None  # type: ignore[assignment]
    opens_at: HHMM = None  # type: ignore[assignment]
    closes_at: HHMM = None  # type: ignore[assignment]
    is_active: StrictBool = None  # type: ignore[assignment]


class RoomOut(BaseModel):
    id: int
    branch_id: int
    code: str
    name: str
    kind: str
    capacity: int
    min_participants: int
    features: list[str]
    opens_at: str
    closes_at: str
    is_active: bool
    created_at: str


def room_out(room: Room) -> RoomOut:
    return RoomOut(
        id=room.id,
        branch_id=room.branch_id,
        code=room.code,
        name=room.name,
        kind=room.kind,
        capacity=room.capacity,
        min_participants=room.min_participants,
        features=list(room.features),
        opens_at=format_time(room.opens_at),
        closes_at=format_time(room.closes_at),
        is_active=room.is_active,
        created_at=format_datetime(room.created_at),
    )


class SlotOut(BaseModel):
    start: str
    end: str
    free: bool
    booking_id: int | None


class AvailabilityOut(BaseModel):
    room_id: int
    date: str
    open: bool
    slots: list[SlotOut]


Purpose = Annotated[str, Field(max_length=200)]


def _check_participants(value: list[int]) -> list[int]:
    if len(set(value)) != len(value):
        raise ValueError("participant_ids must not contain duplicates")
    if len(value) > 11:
        raise ValueError("at most 11 participants are allowed")
    return value


class RoomBookingCreateIn(RequestModel):
    room_id: Id
    member_id: Id | None = None
    date: DateValue
    start_time: HHMM
    end_time: HHMM
    participant_ids: list[Id] = Field(default_factory=list)
    purpose: Purpose = ""

    @field_validator("end_time")
    @classmethod
    def _interval(cls, value: datetime.time, info: ValidationInfo) -> datetime.time:
        start = info.data.get("start_time")
        if start is not None:
            if start >= value:
                raise ValueError("start_time must be before end_time")
            duration = minutes_of(value) - minutes_of(start)
            if not 30 <= duration <= 240:
                raise ValueError("the duration must be between 30 minutes and 4 hours")
        return value

    @field_validator("participant_ids")
    @classmethod
    def _participants(cls, value: list[int]) -> list[int]:
        return _check_participants(value)


class RoomBookingPatchIn(RequestModel):
    participant_ids: list[Id] = None  # type: ignore[assignment]
    purpose: Purpose = None  # type: ignore[assignment]

    @field_validator("participant_ids")
    @classmethod
    def _participants(cls, value: list[int]) -> list[int]:
        return _check_participants(value)


class RoomBookingOut(BaseModel):
    id: int
    room_id: int
    member_id: int
    participant_ids: list[int]
    date: str
    start_time: str
    end_time: str
    status: str
    purpose: str
    created_at: str
    created_by: int
    checked_in_at: str | None
    closed_at: str | None
    cancel_reason: str | None
    late_cancellation: bool
    room_code: str
    branch_id: int
    duration_minutes: int


def booking_out(booking: RoomBooking, room: Room) -> RoomBookingOut:
    return RoomBookingOut(
        id=booking.id,
        room_id=booking.room_id,
        member_id=booking.member_id,
        participant_ids=booking.participant_ids,
        date=booking.date.isoformat(),
        start_time=format_time(booking.start_time),
        end_time=format_time(booking.end_time),
        status=booking.status,
        purpose=booking.purpose,
        created_at=format_datetime(booking.created_at),
        created_by=booking.created_by,
        checked_in_at=format_datetime(booking.checked_in_at) if booking.checked_in_at is not None else None,
        closed_at=format_datetime(booking.closed_at) if booking.closed_at is not None else None,
        cancel_reason=booking.cancel_reason,
        late_cancellation=booking.late_cancellation,
        room_code=room.code,
        branch_id=room.branch_id,
        duration_minutes=booking.duration_minutes,
    )


class ProcessOut(BaseModel):
    no_shows: int
    completed: int
    bans: int


class RoomRemindersOut(BaseModel):
    room_reminders: int


class RoomBanCreateIn(RequestModel):
    starts_on: DateValue
    ends_on: DateValue
    note: Annotated[str, Field(max_length=500)] = ""


class RoomBanOut(BaseModel):
    id: int
    member_id: int
    starts_on: str
    ends_on: str
    reason: str
    note: str
    created_at: str
    created_by: int | None
    lifted_at: str | None
    lifted_by: int | None
    in_force: bool


def ban_out(ban: RoomBan, today: datetime.date) -> RoomBanOut:
    return RoomBanOut(
        id=ban.id,
        member_id=ban.member_id,
        starts_on=ban.starts_on.isoformat(),
        ends_on=ban.ends_on.isoformat(),
        reason=ban.reason,
        note=ban.note,
        created_at=format_datetime(ban.created_at),
        created_by=ban.created_by,
        lifted_at=format_datetime(ban.lifted_at) if ban.lifted_at is not None else None,
        lifted_by=ban.lifted_by,
        in_force=ban.in_force_on(today),
    )


class RoomUsageOut(BaseModel):
    room_id: int
    room_code: str
    branch_id: int
    open_hours: str
    booked_hours: str
    used_hours: str
    no_shows: int
    late_cancellations: int
    utilization: str


class RoomSummaryOut(BaseModel):
    upcoming_bookings: int
    banned_until: str | None
    hours_this_week: str
