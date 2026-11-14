"""Opening hours, closures and open days (LIB-STF-07 to LIB-STF-14)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.calendar import is_working_day
from lms.core.clock import LOCAL_TZ
from lms.core.errors import Conflict, ValidationFailed
from lms.equipment.inventory import cancel_reservation as cancel_equipment_reservation
from lms.equipment.models import EquipmentReservation
from lms.events.events import cancel_for_closure as cancel_events_for_closure
from lms.rooms.lifecycle import cancel_booking
from lms.rooms.models import Room, RoomBooking
from lms.rooms.schemas import format_time
from lms.staff import shifts
from lms.staff.models import BranchHours, Closure, Shift
from lms.staff.schedule import (
    DEFAULT_CLOSES,
    DEFAULT_MIN_STAFF,
    DEFAULT_OPENS,
    has_closure_on,
    hours_of,
    load_schedule,
)
from lms.staff.schemas import ClosureCreatedOut, ClosureOut, HoursOut, OpenDayOut

MAX_OPEN_DAYS = 62


def hours_out(db: Session, branch_id: int) -> HoursOut:
    """LIB-STF-07: a branch without a record has the default values."""
    record_ = hours_of(db, branch_id)
    opens, closes, min_staff = (
        (DEFAULT_OPENS, DEFAULT_CLOSES, DEFAULT_MIN_STAFF)
        if record_ is None
        else (record_.opens_at, record_.closes_at, record_.min_staff)
    )
    return HoursOut(
        branch_id=branch_id, opens_at=format_time(opens), closes_at=format_time(closes), min_staff=min_staff
    )


def hours_problems(opens_at: datetime.time, closes_at: datetime.time, min_staff: int) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    if opens_at >= closes_at:
        problems.append({"field": "closes_at", "problem": "closes_at must be after opens_at"})
    elif (closes_at.hour * 60 + closes_at.minute) - (opens_at.hour * 60 + opens_at.minute) < 240:
        problems.append({"field": "closes_at", "problem": "the branch must be open at least 4 hours"})
    if not 1 <= min_staff <= 10:
        problems.append({"field": "min_staff", "problem": "min_staff must be between 1 and 10"})
    return problems


def set_hours(
    db: Session,
    now: datetime.datetime,
    actor: User,
    branch: Branch,
    opens_at: datetime.time,
    closes_at: datetime.time,
    min_staff: int,
) -> HoursOut:
    """LIB-STF-08."""
    problems = hours_problems(opens_at, closes_at, min_staff)
    if problems:
        raise ValidationFailed(problems)
    outside = [
        s.id
        for s in db.scalars(
            sa.select(Shift)
            .where(Shift.branch_id == branch.id, Shift.status.in_(("planned", "completed")), Shift.date > now.date())
            .order_by(Shift.id)
        )
        if s.start_time < opens_at or s.end_time > closes_at
    ]
    if outside:
        raise Conflict(
            "Planned shifts would be outside the new opening hours",
            code="SHIFTS_OUTSIDE_HOURS",
            details={"shift_ids": outside},
        )
    current = hours_of(db, branch.id)
    old = {"opens_at": DEFAULT_OPENS, "closes_at": DEFAULT_CLOSES, "min_staff": DEFAULT_MIN_STAFF}
    if current is not None:
        old = {"opens_at": current.opens_at, "closes_at": current.closes_at, "min_staff": current.min_staff}
    else:
        current = BranchHours(branch_id=branch.id)
        db.add(current)
    current.opens_at, current.closes_at, current.min_staff = opens_at, closes_at, min_staff
    new = {"opens_at": opens_at, "closes_at": closes_at, "min_staff": min_staff}
    diff = changes(
        {k: format_time(v) if isinstance(v, datetime.time) else v for k, v in old.items()},
        {k: format_time(v) if isinstance(v, datetime.time) else v for k, v in new.items()},
    )
    db.flush()
    record(
        db,
        at=now,
        event="branch_hours_updated",
        actor_user_id=actor.id,
        entity_type="branch_hours",
        entity_id=branch.id,
        details=diff,
    )
    return hours_out(db, branch.id)


# --- closures ----------------------------------------------------------------------------------------


def closure_out(closure: Closure) -> ClosureOut:
    return ClosureOut(
        id=closure.id,
        branch_id=closure.branch_id,
        date=closure.date,
        reason=closure.reason,
        created_by=closure.created_by,
    )


def add_closure(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    branch: Branch,
    day: datetime.date,
    reason: str,
) -> ClosureCreatedOut:
    """LIB-STF-10, LIB-STF-11."""
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive", code="BRANCH_INACTIVE", details={"field": "branch_id", "id": branch.id}
        )
    if day <= now.date():
        raise ValidationFailed.single("date", "date must be after today")
    if not is_working_day(day, holidays):
        raise Conflict("The date is not a working day", code="NOT_A_WORKING_DAY", details={"date": day.isoformat()})
    if has_closure_on(db, branch.id, day):
        raise Conflict("The branch already has a closure on this date", details={"field": "date"})
    closure = Closure(branch_id=branch.id, date=day, reason=reason, created_by=actor.id)
    db.add(closure)
    db.flush()
    record(
        db,
        at=now,
        event="branch_closure_added",
        actor_user_id=actor.id,
        entity_type="closure",
        entity_id=closure.id,
        details={"branch_id": branch.id, "date": day.isoformat(), "reason": reason},
    )

    cancelled_shifts = shifts.planned_shifts(db, Shift.branch_id == branch.id, Shift.date == day)
    for shift in cancelled_shifts:
        shifts.cancel_shift(db, now, actor.id, shift, "branch_closed")

    room_bookings = list(
        db.scalars(
            sa.select(RoomBooking)
            .join(Room, Room.id == RoomBooking.room_id)
            .where(Room.branch_id == branch.id, RoomBooking.date == day, RoomBooking.status == "booked")
            .order_by(RoomBooking.start_time, RoomBooking.id)
        )
    )
    for booking in room_bookings:
        cancel_booking(db, now, actor.id, booking, "branch_closed")

    start = datetime.datetime.combine(day, datetime.time.min, LOCAL_TZ)
    reservations = list(
        db.scalars(
            sa.select(EquipmentReservation)
            .where(
                EquipmentReservation.branch_id == branch.id,
                EquipmentReservation.status == "booked",
                EquipmentReservation.starts_at >= start,
                EquipmentReservation.starts_at < start + datetime.timedelta(days=1),
            )
            .order_by(EquipmentReservation.starts_at, EquipmentReservation.id)
        )
    )
    for reservation in reservations:
        cancel_equipment_reservation(db, now, actor.id, reservation, "branch_closed")

    cancelled_events = cancel_events_for_closure(db, now, actor, branch.id, day)  # LIB-EVT-12

    return ClosureCreatedOut(
        **closure_out(closure).model_dump(),
        cancelled_shifts=len(cancelled_shifts),
        cancelled_room_bookings=len(room_bookings),
        cancelled_equipment_reservations=len(reservations),
        cancelled_events=cancelled_events,
    )


def remove_closure(db: Session, now: datetime.datetime, actor: User, closure: Closure) -> None:
    """LIB-STF-12."""
    if closure.date <= now.date():
        raise Conflict("A closure in the past or today cannot be removed", code="CLOSURE_IN_PAST")
    details: dict[str, Any] = {
        "branch_id": closure.branch_id,
        "date": closure.date.isoformat(),
        "reason": closure.reason,
    }
    entity_id = closure.id
    db.delete(closure)
    record(
        db,
        at=now,
        event="branch_closure_removed",
        actor_user_id=actor.id,
        entity_type="closure",
        entity_id=entity_id,
        details=details,
    )


def closure_list_stmt(
    *,
    branch_id: int | None = None,
    first: datetime.date | None = None,
    last: datetime.date | None = None,
) -> sa.Select[tuple[Closure]]:
    """LIB-STF-13."""
    stmt = sa.select(Closure).order_by(Closure.date, Closure.branch_id, Closure.id)
    if branch_id is not None:
        stmt = stmt.where(Closure.branch_id == branch_id)
    if first is not None:
        stmt = stmt.where(Closure.date >= first)
    if last is not None:
        stmt = stmt.where(Closure.date <= last)
    return stmt


def open_days(
    db: Session,
    holidays: Container[datetime.date],
    branch_id: int,
    first: datetime.date,
    last: datetime.date,
) -> list[OpenDayOut]:
    """LIB-STF-14."""
    schedule = load_schedule(db, branch_id)
    days: list[OpenDayOut] = []
    day = first
    while day <= last:
        reason = schedule.closed_reason(day, holidays)
        days.append(
            OpenDayOut(
                date=day,
                open=reason is None,
                reason=reason,
                opens_at=format_time(schedule.opens_at) if reason is None else None,
                closes_at=format_time(schedule.closes_at) if reason is None else None,
            )
        )
        day += datetime.timedelta(days=1)
    return days
