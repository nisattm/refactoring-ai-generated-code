"""Rooms, availability and free rooms (LIB-ROOM-01 to LIB-ROOM-09)."""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.branches.service import require_active_branch
from lms.core.calendar import is_working_day
from lms.core.errors import Conflict, NotFound, ValidationFailed
from lms.events.queries import events_using_room
from lms.rooms.lifecycle import cancel_booking
from lms.rooms.models import Room, RoomBooking
from lms.rooms.queries import bookings_on, is_active, is_person
from lms.rooms.rules import ACTIVE_STATUSES
from lms.rooms.schemas import (
    AvailabilityOut,
    SlotOut,
    format_time,
    room_capacity_problems,
    room_hours_problems,
)
from lms.staff.schedule import has_closure_on

_SLOT = datetime.timedelta(minutes=30)


def get_room_or_404(db: Session, room_id: int) -> Room:
    room = db.get(Room, room_id)
    if room is None:
        raise NotFound(f"Room {room_id} does not exist", details={"resource": "room", "id": room_id})
    return room


def _snapshot(room: Room) -> dict[str, Any]:
    return {
        "name": room.name,
        "features": list(room.features),
        "capacity": room.capacity,
        "min_participants": room.min_participants,
        "opens_at": format_time(room.opens_at),
        "closes_at": format_time(room.closes_at),
        "is_active": room.is_active,
    }


def create_room(
    db: Session,
    now: datetime.datetime,
    actor: User,
    *,
    branch_id: int,
    code: str,
    name: str,
    kind: str,
    capacity: int | None,
    min_participants: int | None,
    features: list[str],
    opens_at: datetime.time,
    closes_at: datetime.time,
) -> Room:
    """LIB-ROOM-01, LIB-ROOM-02."""
    problems: list[dict[str, str]] = []
    if kind == "individual":
        capacity = 1 if capacity is None else capacity
        min_participants = 1 if min_participants is None else min_participants
    else:
        if capacity is None:
            problems.append({"field": "capacity", "problem": "capacity is required for a group room"})
        if min_participants is None:
            problems.append({"field": "min_participants", "problem": "min_participants is required for a group room"})
    if capacity is not None and min_participants is not None:
        problems += room_capacity_problems(kind, capacity, min_participants)
    problems += room_hours_problems(opens_at, closes_at)
    if problems:
        raise ValidationFailed(problems)
    assert capacity is not None and min_participants is not None

    require_active_branch(db, "branch_id", branch_id)
    if db.scalar(sa.select(Room.id).where(Room.branch_id == branch_id, Room.code == code)) is not None:
        raise Conflict("A room with this code already exists in the branch", details={"field": "code"})
    room = Room(
        branch_id=branch_id,
        code=code,
        name=name,
        kind=kind,
        capacity=capacity,
        min_participants=min_participants,
        features=features,
        opens_at=opens_at,
        closes_at=closes_at,
        is_active=True,
        created_at=now,
    )
    db.add(room)
    db.flush()
    record(
        db,
        at=now,
        event="room_created",
        actor_user_id=actor.id,
        entity_type="room",
        entity_id=room.id,
        details={"branch_id": branch_id, "code": code, "name": name, "kind": kind, **_snapshot(room)},
    )
    return room


def _conflicting_bookings(
    db: Session, now: datetime.datetime, room: Room, new: dict[str, Any], fields: dict[str, Any]
) -> list[int]:
    """LIB-ROOM-05: active bookings with a future start that the new values would break."""
    statuses = ("checked_in",) if fields.get("is_active") is False else ACTIVE_STATUSES
    stmt = sa.select(RoomBooking).where(
        RoomBooking.room_id == room.id, RoomBooking.status.in_(statuses), RoomBooking.date >= now.date()
    )
    ids: list[int] = []
    for booking in db.scalars(stmt):
        if booking.start_at <= now:
            continue
        persons = len(booking.person_ids)
        outside = ("opens_at" in fields or "closes_at" in fields) and (
            booking.start_time < new["opens_at"] or booking.end_time > new["closes_at"]
        )
        too_many = "capacity" in fields and persons > new["capacity"]
        too_few = "min_participants" in fields and persons < new["min_participants"]
        if outside or too_many or too_few:
            ids.append(booking.id)
    return sorted(ids)


def update_room(db: Session, now: datetime.datetime, actor: User, room: Room, fields: dict[str, Any]) -> Room:
    """LIB-ROOM-04 to LIB-ROOM-06. ``fields`` holds only the fields present in the request."""
    new = {
        name: fields.get(name, getattr(room, name))
        for name in ("name", "features", "capacity", "min_participants", "opens_at", "closes_at", "is_active")
    }
    problems = room_capacity_problems(room.kind, new["capacity"], new["min_participants"])
    problems += room_hours_problems(new["opens_at"], new["closes_at"])
    if problems:
        raise ValidationFailed(problems)

    conflicts = _conflicting_bookings(db, now, room, new, fields)
    if conflicts:
        raise Conflict(
            "The change conflicts with active bookings",
            code="ROOM_HAS_BOOKINGS",
            details={"booking_ids": conflicts},
        )

    old = _snapshot(room)
    deactivating = room.is_active and new["is_active"] is False
    for name, value in new.items():
        setattr(room, name, list(value) if name == "features" else value)
    diff = changes(old, _snapshot(room))
    if diff:
        record(
            db, at=now, event="room_updated", actor_user_id=actor.id, entity_type="room", entity_id=room.id, details=diff
        )
    if deactivating:
        stmt = (
            sa.select(RoomBooking)
            .where(RoomBooking.room_id == room.id, RoomBooking.status == "booked", RoomBooking.date >= now.date())
            .order_by(RoomBooking.date, RoomBooking.start_time, RoomBooking.id)
        )
        for booking in list(db.scalars(stmt)):
            if booking.start_at > now:
                cancel_booking(db, now, actor.id, booking, "room_closed")
    return room


# --- availability ---------------------------------------------------------------------


def is_open_on(db: Session, room: Room, day: datetime.date, holidays: Container[datetime.date]) -> bool:
    """LIB-ROOM-07."""
    if not room.is_active or not is_working_day(day, holidays):
        return False
    branch = db.get(Branch, room.branch_id)
    return branch is not None and branch.is_active and not has_closure_on(db, room.branch_id, day)


def _slots(room: Room) -> list[tuple[datetime.time, datetime.time]]:
    anchor = datetime.date(2000, 1, 1)
    cursor = datetime.datetime.combine(anchor, room.opens_at)
    end = datetime.datetime.combine(anchor, room.closes_at)
    slots = []
    while cursor < end:
        slots.append((cursor.time(), (cursor + _SLOT).time()))
        cursor += _SLOT
    return slots


def availability(
    db: Session,
    now: datetime.datetime,
    room: Room,
    day: datetime.date,
    holidays: Container[datetime.date],
    *,
    staff: bool,
    member_id: int | None,
) -> AvailabilityOut:
    """LIB-ROOM-08."""
    if not is_open_on(db, room, day, holidays):
        return AvailabilityOut(room_id=room.id, date=day.isoformat(), open=False, slots=[])
    active = [b for b in bookings_on(db, day, ACTIVE_STATUSES) if b.room_id == room.id and is_active(b, now)]
    events = events_using_room(db, room.id, day)  # LIB-EVT-11
    slots: list[SlotOut] = []
    for start, end in _slots(room):
        booking = next((b for b in active if b.start_time <= start and end <= b.end_time), None)
        in_event = any(e.start_time < end and start < e.end_time for e in events)
        shown = booking is not None and (staff or (member_id is not None and is_person(booking, member_id)))
        slots.append(
            SlotOut(
                start=format_time(start),
                end=format_time(end),
                free=booking is None and not in_event,
                booking_id=booking.id if shown and booking is not None else None,
            )
        )
    return AvailabilityOut(room_id=room.id, date=day.isoformat(), open=True, slots=slots)


def filter_rooms(
    db: Session,
    *,
    branch_id: int | None = None,
    kind: str | None = None,
    is_active: bool | None = None,
    min_capacity: int | None = None,
    features: list[str] | None = None,
) -> list[Room]:
    """LIB-ROOM-03: rooms ordered by branch and code."""
    stmt = sa.select(Room).order_by(Room.branch_id, Room.code, Room.id)
    if branch_id is not None:
        stmt = stmt.where(Room.branch_id == branch_id)
    if kind is not None:
        stmt = stmt.where(Room.kind == kind)
    if is_active is not None:
        stmt = stmt.where(Room.is_active == is_active)
    if min_capacity is not None:
        stmt = stmt.where(Room.capacity >= min_capacity)
    rooms = list(db.scalars(stmt))
    if features:
        rooms = [r for r in rooms if all(f in r.features for f in features)]
    return rooms


def free_rooms(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    day: datetime.date,
    start: datetime.time,
    end: datetime.time,
    **filters: Any,
) -> list[Room]:
    """LIB-ROOM-09."""
    busy: dict[int, list[RoomBooking]] = defaultdict(list)
    for booking in bookings_on(db, day, ACTIVE_STATUSES):
        if is_active(booking, now):
            busy[booking.room_id].append(booking)
    result = []
    for room in filter_rooms(db, **filters):
        if not is_open_on(db, room, day, holidays):
            continue
        if start < room.opens_at or end > room.closes_at:
            continue
        if any(b.start_time < end and start < b.end_time for b in busy[room.id]):
            continue
        if any(e.start_time < end and start < e.end_time for e in events_using_room(db, room.id, day)):
            continue
        result.append(room)
    return result
