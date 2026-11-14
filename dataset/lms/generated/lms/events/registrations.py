"""Registrations, cancellation and attendance (LIB-EVT-19 to LIB-EVT-32)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.core.errors import Conflict, NotFound
from lms.core.money import format_amount
from lms.events import queries
from lms.events.lifecycle import issue_fee, mark_cancelled, promote_waiting, waive_fee
from lms.events.models import Event, EventRegistration
from lms.events.rules import (
    CHECK_IN_EARLY,
    DEBT_BLOCK,
    EVENT_RULES,
    REGISTRATION_CLOSES_BEFORE,
    TIMELY_CANCELLATION,
    WAIVE_TIMELY,
)
from lms.events.schemas import RegistrationOut, registration_out
from lms.fines import service as fines
from lms.members.models import Member


def _error(code: str, message: str, **details: Any) -> Conflict:
    return Conflict(message, code=code, details=details)


def get_registration_or_404(db: Session, registration_id: int) -> EventRegistration:
    reg = db.get(EventRegistration, registration_id)
    if reg is None:
        raise NotFound(
            f"Event registration {registration_id} does not exist",
            details={"resource": "event_registration", "id": registration_id},
        )
    return reg


def to_out(db: Session, reg: EventRegistration, event: Event | None = None) -> RegistrationOut:
    if event is None:
        event = db.get(Event, reg.event_id)
        assert event is not None
    return registration_out(reg, event, queries.position_of(db, reg))


# --- register ----------------------------------------------------------------------------------


def _check_member(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    event: Event,
    member: Member,
) -> None:
    """Steps (3) to (7) of LIB-EVT-20."""
    if member.status == "passive":
        raise _error("MEMBER_PASSIVE", "The member is passive")
    if event.date > member.valid_until:
        raise _error("MEMBERSHIP_EXPIRED", "The membership is not valid on the event date")
    rules = EVENT_RULES[member.membership_type]
    if event.audience not in rules.audiences:
        raise _error("EVENT_NOT_FOR_TYPE", "The event is not open to this membership type", audience=event.audience)
    bans = queries.bans_in_force(db, member.id, now.date(), event.date)
    if bans:
        raise _error(
            "MEMBER_BANNED_FROM_EVENTS",
            "The member is banned from events",
            ends_on=max(b.ends_on for b in bans).isoformat(),
        )
    debt = fines.outstanding_fees(db, member.id) + fines.accrued_late_fees(db, member.id, now, holidays)
    if debt >= DEBT_BLOCK:
        raise _error("MEMBER_BLOCKED_BY_DEBT", "The member's debt blocks registrations", total_debt=format_amount(debt))


def register(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    actor: User,
    event: Event,
    member: Member,
) -> EventRegistration:
    """LIB-EVT-19 to LIB-EVT-21."""
    if event.status != "published":
        raise _error("EVENT_NOT_OPEN", "The event is not open for registration", status=event.status)
    if now >= event.start_at - REGISTRATION_CLOSES_BEFORE:
        raise _error("REGISTRATION_CLOSED", "Registration closes 1 hour before the start")
    _check_member(db, now, holidays, event, member)

    if db.scalar(
        sa.select(EventRegistration.id).where(
            EventRegistration.event_id == event.id,
            EventRegistration.member_id == member.id,
            EventRegistration.status.in_(("registered", "waitlisted")),
        )
    ):
        raise _error("ALREADY_REGISTERED", "The member is already registered for this event")
    upcoming = queries.active_upcoming_registrations(db, member.id, now)
    clashing = sorted(
        e.id
        for r, e in upcoming
        if r.status == "registered"
        and e.id != event.id
        and e.date == event.date
        and queries.overlaps(event.start_time, event.end_time, e.start_time, e.end_time)
    )
    if clashing:
        raise _error("EVENT_TIME_CONFLICT", "The member has an overlapping registration", event_id=clashing[0])
    limit = EVENT_RULES[member.membership_type].limit
    if len(upcoming) >= limit:
        raise _error("EVENT_REGISTRATION_LIMIT_REACHED", "The registration limit is reached", limit=limit)
    registered = queries.count_with_status(db, event.id, "registered")
    waitlisted = queries.count_with_status(db, event.id, "waitlisted")
    full = registered >= event.capacity
    if full and waitlisted >= event.capacity:
        raise _error("WAITLIST_FULL", "The waiting list is full")

    reg = EventRegistration(
        event_id=event.id,
        member_id=member.id,
        status="waitlisted" if full else "registered",
        created_at=now,
        late_cancellation=False,
    )
    db.add(reg)
    db.flush()
    record(
        db,
        at=now,
        event="event_registration_created",
        actor_user_id=actor.id,
        entity_type="event_registration",
        entity_id=reg.id,
        details={"event_id": event.id, "member_id": member.id, "status": reg.status},
    )
    if reg.status == "registered":
        issue_fee(db, now, actor, event, reg)
    return reg


# --- cancel ------------------------------------------------------------------------------------


def cancel(
    db: Session, now: datetime.datetime, actor: User, reg: EventRegistration, *, by_member: bool
) -> EventRegistration:
    """LIB-EVT-27 to LIB-EVT-29, LIB-EVT-31."""
    if not reg.is_active:
        raise _error("REGISTRATION_NOT_ACTIVE", "The registration is not active", status=reg.status)
    event = db.get(Event, reg.event_id)
    assert event is not None
    if now >= event.start_at:
        raise _error("EVENT_STARTED", "The event has already started")
    was_registered = reg.status == "registered"
    timely = now <= event.start_at - TIMELY_CANCELLATION
    late = was_registered and not timely
    mark_cancelled(db, now, actor, reg, "member_request" if by_member else "staff_request", late=late)
    if was_registered and timely:
        waive_fee(db, now, actor, reg, WAIVE_TIMELY, unpaid_only=True)
    if was_registered:
        db.flush()
        promote_waiting(db, now, actor, event)
    return reg


# --- check-in ----------------------------------------------------------------------------------


def check_in(db: Session, now: datetime.datetime, actor: User, reg: EventRegistration) -> EventRegistration:
    """LIB-EVT-32."""
    if reg.status != "registered":
        raise _error("REGISTRATION_NOT_ACTIVE", "The registration is not registered", status=reg.status)
    event = db.get(Event, reg.event_id)
    assert event is not None
    if now < event.start_at - CHECK_IN_EARLY:
        raise _error("CHECK_IN_NOT_OPEN", "Check-in is not open yet")
    if now >= event.end_at:
        raise _error("EVENT_OVER", "The event is over")
    reg.status = "attended"
    reg.attended_at = now
    record(
        db,
        at=now,
        event="event_attended",
        actor_user_id=actor.id,
        entity_type="event_registration",
        entity_id=reg.id,
        details={"event_id": event.id, "member_id": reg.member_id},
    )
    return reg


# --- lists -------------------------------------------------------------------------------------


_STATUS_RANK = sa.case(
    (EventRegistration.status == "registered", 0), (EventRegistration.status == "waitlisted", 1), else_=2
)


def event_registrations_stmt(event_id: int, status: str | None) -> sa.Select[tuple[EventRegistration]]:
    """LIB-EVT-22."""
    stmt = (
        sa.select(EventRegistration)
        .where(EventRegistration.event_id == event_id)
        .order_by(_STATUS_RANK, EventRegistration.created_at, EventRegistration.id)
    )
    if status is not None:
        stmt = stmt.where(EventRegistration.status == status)
    return stmt


def member_registrations_stmt(
    member_id: int, status: str | None, first: datetime.date | None, last: datetime.date | None
) -> sa.Select[tuple[EventRegistration]]:
    stmt = (
        sa.select(EventRegistration)
        .join(Event, Event.id == EventRegistration.event_id)
        .where(EventRegistration.member_id == member_id)
        .order_by(Event.date, Event.start_time, EventRegistration.id)
    )
    if status is not None:
        stmt = stmt.where(EventRegistration.status == status)
    if first is not None:
        stmt = stmt.where(Event.date >= first)
    if last is not None:
        stmt = stmt.where(Event.date <= last)
    return stmt
