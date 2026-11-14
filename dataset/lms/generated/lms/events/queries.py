"""Light-weight lookups of module 20 used by other modules (rooms, branches, staff, members) and by module 20 itself.

This module imports only models, so that the other modules can use it without import cycles."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.events.models import (
    ACTIVE_REGISTRATION_STATUSES,
    Event,
    EventBan,
    EventRegistration,
)
from lms.staff.models import COUNTING_STATUSES, Shift

OPEN_STATUSES = ("draft", "published")


def overlaps(a_start: datetime.time, a_end: datetime.time, b_start: datetime.time, b_end: datetime.time) -> bool:
    return a_start < b_end and b_start < a_end


# --- events ----------------------------------------------------------------------------------


def upcoming_or_draft(db: Session, *conditions: sa.ColumnElement[bool], now: datetime.datetime) -> list[Event]:
    """``draft`` events and upcoming ``published`` events matching ``conditions``, ordered by start and id."""
    stmt = (
        sa.select(Event)
        .where(Event.status.in_(OPEN_STATUSES), Event.date >= now.date(), *conditions)
        .order_by(Event.date, Event.start_time, Event.id)
    )
    return [e for e in db.scalars(stmt) if e.status == "draft" or e.start_at > now]


def branch_has_open_events(db: Session, branch_id: int, now: datetime.datetime) -> bool:
    """LIB-EVT-42: a ``draft`` or upcoming ``published`` event (a ``draft`` counts whatever its date)."""
    if db.scalar(sa.select(Event.id).where(Event.branch_id == branch_id, Event.status == "draft").limit(1)) is not None:
        return True
    published = db.scalars(
        sa.select(Event).where(Event.branch_id == branch_id, Event.status == "published", Event.date >= now.date())
    )
    return any(e.start_at > now for e in published)


def open_event_ids_of_staff(db: Session, staff_id: int, now: datetime.datetime) -> list[int]:
    """LIB-EVT-43: ids of the ``draft`` and upcoming ``published`` events a staff profile is responsible for."""
    stmt = sa.select(Event).where(Event.staff_id == staff_id, Event.status.in_(OPEN_STATUSES))
    return sorted(e.id for e in db.scalars(stmt) if e.status == "draft" or e.start_at > now)


def events_using_room(
    db: Session,
    room_id: int,
    day: datetime.date,
    *,
    statuses: tuple[str, ...] = OPEN_STATUSES,
    exclude_id: int | None = None,
) -> list[Event]:
    stmt = sa.select(Event).where(Event.room_id == room_id, Event.date == day, Event.status.in_(statuses))
    if exclude_id is not None:
        stmt = stmt.where(Event.id != exclude_id)
    return list(db.scalars(stmt.order_by(Event.start_time, Event.id)))


def room_event_conflict(
    db: Session, room_id: int, day: datetime.date, start: datetime.time, end: datetime.time
) -> Event | None:
    """LIB-EVT-11: the first ``draft`` or ``published`` event that uses the room in the interval."""
    for event in events_using_room(db, room_id, day):
        if overlaps(start, end, event.start_time, event.end_time):
            return event
    return None


def staff_covered(db: Session, event: Event) -> bool:
    """LIB-EVT-03 (9), LIB-EVT-09: a counting shift of the responsible staff member at the event's branch on
    the date that covers the whole interval."""
    stmt = (
        sa.select(Shift.id)
        .where(
            Shift.staff_id == event.staff_id,
            Shift.branch_id == event.branch_id,
            Shift.date == event.date,
            Shift.status.in_(COUNTING_STATUSES),
            Shift.start_time <= event.start_time,
            Shift.end_time >= event.end_time,
        )
        .limit(1)
    )
    return db.scalar(stmt) is not None


# --- registrations ---------------------------------------------------------------------------


def count_with_status(db: Session, event_id: int, *statuses: str) -> int:
    stmt = sa.select(sa.func.count()).select_from(EventRegistration).where(
        EventRegistration.event_id == event_id, EventRegistration.status.in_(statuses)
    )
    return db.scalar(stmt) or 0


def has_registration(db: Session, event_id: int) -> bool:
    return db.scalar(sa.select(EventRegistration.id).where(EventRegistration.event_id == event_id).limit(1)) is not None


def waiting_list(db: Session, event_id: int) -> list[EventRegistration]:
    """Waitlisted registrations in order of position."""
    stmt = (
        sa.select(EventRegistration)
        .where(EventRegistration.event_id == event_id, EventRegistration.status == "waitlisted")
        .order_by(EventRegistration.created_at, EventRegistration.id)
    )
    return list(db.scalars(stmt))


def position_of(db: Session, registration: EventRegistration) -> int | None:
    """Derived ``position`` (28.1): 1 + the waitlisted registrations of the event created earlier."""
    if registration.status != "waitlisted":
        return None
    earlier = sa.select(sa.func.count()).select_from(EventRegistration).where(
        EventRegistration.event_id == registration.event_id,
        EventRegistration.status == "waitlisted",
        sa.or_(
            EventRegistration.created_at < registration.created_at,
            sa.and_(
                EventRegistration.created_at == registration.created_at, EventRegistration.id < registration.id
            ),
        ),
    )
    return 1 + (db.scalar(earlier) or 0)


def active_upcoming_registrations(
    db: Session, member_id: int, now: datetime.datetime, *statuses: str
) -> list[tuple[EventRegistration, Event]]:
    """Active registrations of the member (restricted to ``statuses`` if given) for upcoming events."""
    wanted = statuses or ACTIVE_REGISTRATION_STATUSES
    stmt = (
        sa.select(EventRegistration, Event)
        .join(Event, Event.id == EventRegistration.event_id)
        .where(
            EventRegistration.member_id == member_id,
            EventRegistration.status.in_(wanted),
            Event.status == "published",
            Event.date >= now.date(),
        )
        .order_by(Event.date, Event.start_time, Event.id, EventRegistration.id)
    )
    return [(r, e) for r, e in db.execute(stmt) if e.start_at > now]


# --- bans ------------------------------------------------------------------------------------


def bans_in_force(db: Session, member_id: int, *days: datetime.date) -> list[EventBan]:
    """Bans of the member in force on at least one of ``days``."""
    bans = db.scalars(sa.select(EventBan).where(EventBan.member_id == member_id).order_by(EventBan.id))
    return [ban for ban in bans if any(ban.in_force_on(d) for d in days)]


def latest_ban(db: Session, member_id: int) -> EventBan | None:
    stmt = (
        sa.select(EventBan)
        .where(EventBan.member_id == member_id)
        .order_by(EventBan.starts_on.desc(), EventBan.id.desc())
        .limit(1)
    )
    return db.scalar(stmt)
