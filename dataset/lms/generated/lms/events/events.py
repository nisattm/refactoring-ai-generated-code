"""Events and series (LIB-EVT-01 to LIB-EVT-18)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.clock import LOCAL_TZ
from lms.core.errors import Conflict, NotFound, ValidationFailed, reference_not_found
from lms.core.money import format_amount
from lms.core.text import normalize
from lms.events import queries
from lms.events.lifecycle import (
    active_registrations,
    cancel_event,
    event_label,
    promote_waiting,
)
from lms.events.models import Event, EventSeries
from lms.events.rules import (
    MAX_DURATION_MINUTES,
    MIN_DURATION_MINUTES,
    MIN_LEAD_TO_PUBLISH,
)
from lms.events.schemas import EventOut, event_out
from lms.notifications.service import notify_event
from lms.rooms.models import Room
from lms.rooms.queries import active_bookings_of_room
from lms.rooms.schemas import format_time, minutes_of
from lms.staff.models import StaffProfile
from lms.staff.schedule import load_schedule


def _error(code: str, message: str, **details: Any) -> Conflict:
    return Conflict(message, code=code, details=details)


def get_event_or_404(db: Session, event_id: int) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise NotFound(f"Event {event_id} does not exist", details={"resource": "event", "id": event_id})
    return event


def to_out(db: Session, event: Event) -> EventOut:
    return event_out(
        event,
        registered=queries.count_with_status(db, event.id, "registered"),
        waitlisted=queries.count_with_status(db, event.id, "waitlisted"),
        staff_covered=queries.staff_covered(db, event),
    )


# --- 422 checks -----------------------------------------------------------------------------------------


def shape_problems(
    db: Session,
    *,
    branch_id: int,
    room_id: int | None,
    staff_id: int,
    start: datetime.time,
    end: datetime.time,
    capacity: int,
    check_room: bool = True,
    check_staff: bool = True,
) -> tuple[list[dict[str, str]], Room | None, StaffProfile | None]:
    """The request-level rules of 28.1 that need the database: unknown ``room_id`` / ``staff_id``, a room that is
    not a ``group`` room of the branch, a capacity above the room's, and the 1 to 4 hour duration."""
    problems: list[dict[str, str]] = []
    length = minutes_of(end) - minutes_of(start)
    if start >= end:
        problems.append({"field": "end_time", "problem": "end_time must be after start_time"})
    elif not MIN_DURATION_MINUTES <= length <= MAX_DURATION_MINUTES:
        problems.append({"field": "end_time", "problem": "an event must last 1 to 4 hours"})
    room: Room | None = None
    if room_id is not None:
        room = db.get(Room, room_id)
        if room is None:
            if check_room:
                problems.append({"field": "room_id", "problem": f"room {room_id} does not exist"})
        elif room.kind != "group" or room.branch_id != branch_id:
            if check_room:
                problems.append({"field": "room_id", "problem": "room_id must be a group room of the event's branch"})
        elif capacity > room.capacity and check_room:
            problems.append({"field": "capacity", "problem": f"capacity must not exceed the room capacity {room.capacity}"})
    staff = db.get(StaffProfile, staff_id)
    if staff is None and check_staff:
        problems.append({"field": "staff_id", "problem": f"staff {staff_id} does not exist"})
    return problems, room, staff


# --- LIB-EVT-02 -----------------------------------------------------------------------------------------


def check_event(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    branch: Branch,
    room: Room | None,
    staff: StaffProfile,
    day: datetime.date,
    start: datetime.time,
    end: datetime.time,
    *,
    exclude_id: int | None = None,
) -> None:
    """The seven checks of LIB-EVT-02, in order."""
    if not branch.is_active:
        raise _error("BRANCH_INACTIVE", f"Branch {branch.code} is inactive", field="branch_id", id=branch.id)
    if datetime.datetime.combine(day, start, LOCAL_TZ) <= now:
        raise _error("EVENT_IN_PAST", "The event does not start in the future")
    schedule = load_schedule(db, branch.id)
    reason = schedule.closed_reason(day, holidays)
    if reason is not None:
        raise _error(
            "BRANCH_NOT_OPEN", "The branch is not open on this date", reason=reason.split(":")[0], date=day.isoformat()
        )
    outside = start < schedule.opens_at or end > schedule.closes_at
    if room is not None and (start < room.opens_at or end > room.closes_at):
        outside = True
    if outside:
        raise _error(
            "OUTSIDE_BRANCH_HOURS",
            "The event is outside the opening hours",
            opens_at=format_time(schedule.opens_at),
            closes_at=format_time(schedule.closes_at),
        )
    if room is not None:
        if not room.is_active:
            raise _error("ROOM_INACTIVE", "The room is inactive", id=room.id)
        for booking in active_bookings_of_room(db, room.id, day, now):
            if queries.overlaps(start, end, booking.start_time, booking.end_time):
                raise _error("ROOM_NOT_AVAILABLE", "The room is booked", booking_id=booking.id)
        for other in queries.events_using_room(db, room.id, day, statuses=("draft", "published", "completed"), exclude_id=exclude_id):
            if queries.overlaps(start, end, other.start_time, other.end_time):
                raise _error("ROOM_NOT_AVAILABLE", "The room is used by another event", event_id=other.id)
    if not staff.is_active:
        raise _error("STAFF_INACTIVE", "The staff profile is inactive")


def check_on_shift(db: Session, event: Event) -> None:
    """LIB-EVT-03 (9)."""
    if not queries.staff_covered(db, event):
        raise _error(
            "STAFF_NOT_ON_SHIFT", "The responsible staff member has no shift covering the event", staff_id=event.staff_id
        )


# --- create ------------------------------------------------------------------------------------------


def _snapshot(event: Event) -> dict[str, Any]:
    return {
        "title": event.title,
        "description": event.description,
        "room_id": event.room_id,
        "date": event.date.isoformat(),
        "start_time": format_time(event.start_time),
        "end_time": format_time(event.end_time),
        "capacity": event.capacity,
        "fee": format_amount(event.fee),
        "staff_id": event.staff_id,
    }


def _branch_or_404(db: Session, branch_id: int) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise reference_not_found("branch_id", branch_id)
    return branch


def _new_event(
    db: Session,
    now: datetime.datetime,
    actor: User,
    data: dict[str, Any],
    day: datetime.date,
    series_id: int | None,
) -> Event:
    event = Event(
        title=data["title"],
        description=data["description"],
        kind=data["kind"],
        branch_id=data["branch_id"],
        room_id=data["room_id"],
        date=day,
        start_time=data["start_time"],
        end_time=data["end_time"],
        capacity=data["capacity"],
        fee=data["fee"],
        audience=data["audience"],
        staff_id=data["staff_id"],
        series_id=series_id,
        status="draft",
        created_at=now,
    )
    db.add(event)
    db.flush()
    record(
        db,
        at=now,
        event="event_created",
        actor_user_id=actor.id,
        entity_type="event",
        entity_id=event.id,
        details={
            **_snapshot(event),
            "kind": event.kind,
            "branch_id": event.branch_id,
            "audience": event.audience,
            "series_id": series_id,
        },
    )
    return event


def _resolve(db: Session, data: dict[str, Any]) -> tuple[Branch, Room | None, StaffProfile]:
    problems, room, staff = shape_problems(
        db,
        branch_id=data["branch_id"],
        room_id=data["room_id"],
        staff_id=data["staff_id"],
        start=data["start_time"],
        end=data["end_time"],
        capacity=data["capacity"],
    )
    if problems:
        raise ValidationFailed(problems)
    branch = _branch_or_404(db, data["branch_id"])
    assert staff is not None
    return branch, room, staff


def create_event(
    db: Session, now: datetime.datetime, holidays: Container[datetime.date], actor: User, data: dict[str, Any]
) -> Event:
    """LIB-EVT-01, LIB-EVT-02. ``data`` holds every field of LIB-EVT-01 (with defaults filled in)."""
    branch, room, staff = _resolve(db, data)
    check_event(db, now, holidays, branch, room, staff, data["date"], data["start_time"], data["end_time"])
    return _new_event(db, now, actor, data, data["date"], None)


# --- update, publish, cancel -----------------------------------------------------------------------------


def _require_open(event: Event, now: datetime.datetime) -> None:
    if not (event.status == "draft" or event.is_upcoming(now)):
        raise _error("INVALID_EVENT_STATUS", "The event cannot be changed in its status", status=event.status)


def update_event(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    actor: User,
    event: Event,
    fields: dict[str, Any],
) -> Event:
    """LIB-EVT-04 to LIB-EVT-07."""
    new = {
        name: fields.get(name, getattr(event, name))
        for name in ("title", "description", "room_id", "date", "start_time", "end_time", "capacity", "fee", "staff_id")
    }
    problems, room, staff = shape_problems(
        db,
        branch_id=event.branch_id,
        room_id=new["room_id"],
        staff_id=new["staff_id"],
        start=new["start_time"],
        end=new["end_time"],
        capacity=new["capacity"],
        check_room="room_id" in fields or "capacity" in fields,
        check_staff="staff_id" in fields,
    )
    if problems:
        raise ValidationFailed(problems)
    assert staff is not None
    _require_open(event, now)

    branch = _branch_or_404(db, event.branch_id)
    check_event(
        db, now, holidays, branch, room, staff, new["date"], new["start_time"], new["end_time"], exclude_id=event.id
    )
    candidate = Event(
        branch_id=event.branch_id,
        staff_id=new["staff_id"],
        date=new["date"],
        start_time=new["start_time"],
        end_time=new["end_time"],
    )
    if event.status == "published":
        check_on_shift(db, candidate)

    if "fee" in fields and fields["fee"] != event.fee and queries.has_registration(db, event.id):
        raise _error("FEE_LOCKED", "The fee cannot be changed once the event has registrations")
    registered = queries.count_with_status(db, event.id, "registered")
    if "capacity" in fields and fields["capacity"] < registered:
        raise _error(
            "CAPACITY_BELOW_REGISTERED", "The capacity is below the number of registrations", registered=registered
        )

    old = _snapshot(event)
    old_capacity = event.capacity
    for name, value in new.items():
        setattr(event, name, value)
    diff = changes(old, _snapshot(event))
    if diff:
        record(
            db, at=now, event="event_updated", actor_user_id=actor.id, entity_type="event", entity_id=event.id, details=diff
        )
    if event.status == "published" and any(k in diff for k in ("date", "start_time", "end_time", "room_id")):
        for reg in active_registrations(db, event.id):
            notify_event(
                db,
                now,
                reg.member_id,
                "event_changed",
                f"The event {event_label(event)} was changed.",
                event_id=event.id,
            )
    if event.capacity > old_capacity:
        db.flush()
        promote_waiting(db, now, actor, event)
    return event


def publish(
    db: Session, now: datetime.datetime, holidays: Container[datetime.date], actor: User, event: Event
) -> Event:
    """LIB-EVT-03."""
    if event.status != "draft":
        raise _error("INVALID_EVENT_STATUS", "Only a draft event can be published", status=event.status)
    branch = _branch_or_404(db, event.branch_id)
    room = db.get(Room, event.room_id) if event.room_id is not None else None
    staff = db.get(StaffProfile, event.staff_id)
    assert staff is not None
    check_event(
        db, now, holidays, branch, room, staff, event.date, event.start_time, event.end_time, exclude_id=event.id
    )
    if event.start_at - now < MIN_LEAD_TO_PUBLISH:
        raise _error("EVENT_TOO_SOON", "The event starts in less than 24 hours")
    check_on_shift(db, event)
    event.status = "published"
    event.published_at = now
    record(
        db,
        at=now,
        event="event_published",
        actor_user_id=actor.id,
        entity_type="event",
        entity_id=event.id,
        details={"date": event.date.isoformat()},
    )
    return event


def cancel(db: Session, now: datetime.datetime, actor: User, event: Event) -> Event:
    """LIB-EVT-10."""
    _require_open(event, now)
    cancel_event(db, now, actor, event, "staff_request")
    return event


# --- series ------------------------------------------------------------------------------------------


def create_series(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    actor: User,
    data: dict[str, Any],
    first_date: datetime.date,
    weeks: int,
) -> tuple[int, list[int], list[dict[str, Any]]]:
    """LIB-EVT-13, LIB-EVT-14."""
    branch, room, staff = _resolve(db, data)
    valid: list[datetime.date] = []
    skipped: list[dict[str, Any]] = []
    for k in range(weeks):
        day = first_date + datetime.timedelta(days=7 * k)
        try:
            check_event(db, now, holidays, branch, room, staff, day, data["start_time"], data["end_time"])
        except Conflict as exc:
            skipped.append({"date": day, "error_code": exc.code})
        else:
            valid.append(day)
    if not valid:
        raise Conflict(
            "No event of the series can be created",
            code="SERIES_EMPTY",
            details={"skipped": [{"date": s["date"].isoformat(), "error_code": s["error_code"]} for s in skipped]},
        )
    series = EventSeries(created_at=now, created_by=actor.id)
    db.add(series)
    db.flush()
    created = [_new_event(db, now, actor, data, day, series.id).id for day in valid]
    record(
        db,
        at=now,
        event="event_series_created",
        actor_user_id=actor.id,
        entity_type="event_series",
        entity_id=series.id,
        details={"created": created, "skipped": len(skipped), "weeks": weeks, "first_date": first_date.isoformat()},
    )
    return series.id, created, skipped


def cancel_series(db: Session, now: datetime.datetime, actor: User, series_id: int) -> list[int]:
    """LIB-EVT-17."""
    series = db.get(EventSeries, series_id)
    if series is None:
        raise NotFound(f"Event series {series_id} does not exist", details={"resource": "event_series", "id": series_id})
    cancelled: list[int] = []
    for event in queries.upcoming_or_draft(db, Event.series_id == series_id, now=now):
        if event.start_at <= now:  # events that already started are not changed
            continue
        cancel_event(db, now, actor, event, "series_cancelled")
        cancelled.append(event.id)
    record(
        db,
        at=now,
        event="event_series_cancelled",
        actor_user_id=actor.id,
        entity_type="event_series",
        entity_id=series.id,
        details={"cancelled": cancelled},
    )
    return cancelled


# --- closures (LIB-EVT-12) ---------------------------------------------------------------------------


def cancel_for_closure(db: Session, now: datetime.datetime, actor: User, branch_id: int, day: datetime.date) -> int:
    """The ``draft`` and ``published`` events of the branch on a closure date are cancelled (``branch_closed``)."""
    events = db.scalars(
        sa.select(Event)
        .where(Event.branch_id == branch_id, Event.date == day, Event.status.in_(("draft", "published")))
        .order_by(Event.start_time, Event.id)
    ).all()
    for event in events:
        cancel_event(db, now, actor, event, "branch_closed")
    return len(events)


# --- lists -------------------------------------------------------------------------------------------


def list_events(
    db: Session,
    *,
    include_drafts: bool,
    branch_id: int | None = None,
    kind: str | None = None,
    status: str | None = None,
    first: datetime.date | None = None,
    last: datetime.date | None = None,
    series_id: int | None = None,
    q: str | None = None,
) -> sa.Select[tuple[Event]] | list[Event]:
    """LIB-EVT-08. Returns a statement, or a list when ``q`` needs the normalization of LIB-COM-30."""
    stmt = sa.select(Event).order_by(Event.date, Event.start_time, Event.id)
    if not include_drafts:
        stmt = stmt.where(Event.status != "draft")
    if branch_id is not None:
        stmt = stmt.where(Event.branch_id == branch_id)
    if kind is not None:
        stmt = stmt.where(Event.kind == kind)
    if status is not None:
        stmt = stmt.where(Event.status == status)
    if first is not None:
        stmt = stmt.where(Event.date >= first)
    if last is not None:
        stmt = stmt.where(Event.date <= last)
    if series_id is not None:
        stmt = stmt.where(Event.series_id == series_id)
    needle = normalize(q.strip()) if q is not None else ""
    if not needle:
        return stmt
    return [e for e in db.scalars(stmt) if needle in normalize(e.title)]


