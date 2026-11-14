"""Cancellation, promotion and fees of registrations (LIB-EVT-10, 21, 28, 31, 35, 40)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.core.money import ZERO
from lms.events import queries
from lms.events.models import Event, EventRegistration
from lms.events.rules import (
    PROMOTION_CLOSES_BEFORE,
    WAIVE_EVENT_CANCELLED,
    WAIVE_TIMELY,
)
from lms.fines import service as fines
from lms.fines.models import Fee
from lms.notifications.service import notify_event
from lms.rooms.schemas import format_time


def event_label(event: Event) -> str:
    """The title, the date and the times, as in the notifications of LIB-EVT-44."""
    return (
        f'"{event.title}" on {event.date.isoformat()} '
        f"from {format_time(event.start_time)} to {format_time(event.end_time)}"
    )


# --- fees -------------------------------------------------------------------------------------


def issue_fee(db: Session, now: datetime.datetime, actor: User, event: Event, reg: EventRegistration) -> None:
    """LIB-EVT-21: a registration that becomes ``registered`` for an event with a fee gets an ``event_fee``."""
    if event.fee <= ZERO:
        return
    fee = fines.create_fee(
        db,
        now,
        actor,
        member_id=reg.member_id,
        loan_id=None,
        kind="event_fee",
        amount=event.fee,
        event_registration_id=reg.id,
    )
    reg.fee_id = fee.id


def _open_fee(db: Session, reg: EventRegistration) -> Fee | None:
    if reg.fee_id is None:
        return None
    fee = db.get(Fee, reg.fee_id)
    return fee if fee is not None and fee.status == "open" else None


def waive_fee(
    db: Session, now: datetime.datetime, actor: User, reg: EventRegistration, reason: str, *, unpaid_only: bool
) -> None:
    """The automatic waivers of LIB-EVT-10 (any open fee) and LIB-EVT-28 / LIB-EVT-35 (only when nothing is paid)."""
    fee = _open_fee(db, reg)
    if fee is None or (unpaid_only and fee.paid_amount > ZERO):
        return
    fines.waive_fee(db, now, actor, fee, reason)


# --- cancelling registrations --------------------------------------------------------------------


def mark_cancelled(
    db: Session,
    now: datetime.datetime,
    actor: User | None,
    reg: EventRegistration,
    reason: str,
    *,
    late: bool = False,
) -> None:
    """Set a registration to ``cancelled`` (no notification, no fee handling)."""
    reg.status = "cancelled"
    reg.cancelled_at = now
    reg.cancel_reason = reason
    reg.late_cancellation = late
    record(
        db,
        at=now,
        event="event_registration_cancelled",
        actor_user_id=actor.id if actor is not None else None,
        entity_type="event_registration",
        entity_id=reg.id,
        details={"event_id": reg.event_id, "member_id": reg.member_id, "reason": reason, "late_cancellation": late},
    )


def active_registrations(db: Session, event_id: int) -> list[EventRegistration]:
    stmt = (
        sa.select(EventRegistration)
        .where(EventRegistration.event_id == event_id, EventRegistration.status.in_(("registered", "waitlisted")))
        .order_by(EventRegistration.id)
    )
    return list(db.scalars(stmt))


def cancel_event(db: Session, now: datetime.datetime, actor: User, event: Event, reason: str) -> None:
    """LIB-EVT-10: the event becomes ``cancelled``; every active registration is cancelled, its open fee waived and
    its member notified."""
    event.status = "cancelled"
    event.cancel_reason = reason
    record(
        db,
        at=now,
        event="event_cancelled",
        actor_user_id=actor.id,
        entity_type="event",
        entity_id=event.id,
        details={"reason": reason, "date": event.date.isoformat()},
    )
    for reg in active_registrations(db, event.id):
        mark_cancelled(db, now, actor, reg, "event_cancelled")
        waive_fee(db, now, actor, reg, WAIVE_EVENT_CANCELLED, unpaid_only=False)
        notify_event(
            db,
            now,
            reg.member_id,
            "event_cancelled",
            f"The event {event_label(event)} was cancelled.",
            event_id=event.id,
        )


# --- promotion ----------------------------------------------------------------------------------


def promote_waiting(db: Session, now: datetime.datetime, actor: User, event: Event) -> list[EventRegistration]:
    """LIB-EVT-31: promote the first waitlisted registrations while places are free; nobody is promoted
    from start − 1 hour on."""
    promoted: list[EventRegistration] = []
    if event.status != "published" or now >= event.start_at - PROMOTION_CLOSES_BEFORE:
        return promoted
    registered = queries.count_with_status(db, event.id, "registered")
    for reg in queries.waiting_list(db, event.id):
        if registered >= event.capacity:
            break
        reg.status = "registered"
        reg.promoted_at = now
        registered += 1
        promoted.append(reg)
        issue_fee(db, now, actor, event, reg)
        notify_event(
            db,
            now,
            reg.member_id,
            "event_promoted",
            f"A place became free: you are registered for {event_label(event)}.",
            event_id=event.id,
        )
    return promoted


# --- effects on one member's registrations ---------------------------------------------------------


def release_member(
    db: Session,
    now: datetime.datetime,
    actor: User,
    member_id: int,
    reason: str,
    *,
    first: datetime.date | None = None,
    last: datetime.date | None = None,
    waive: bool,
) -> list[int]:
    """LIB-EVT-35, LIB-EVT-40, LIB-EVT-41: cancel the member's active registrations for upcoming events (only
    those whose date lies in ``first``..``last`` if given), waive unpaid open fees if ``waive``, then promote the
    waiting members of the events whose places were freed. Returns the ids of the cancelled registrations."""
    cancelled: list[int] = []
    freed: dict[int, Event] = {}
    for reg, event in queries.active_upcoming_registrations(db, member_id, now):
        if (first is not None and event.date < first) or (last is not None and event.date > last):
            continue
        was_registered = reg.status == "registered"
        mark_cancelled(db, now, actor, reg, reason)
        cancelled.append(reg.id)
        if waive:
            waive_fee(db, now, actor, reg, WAIVE_TIMELY, unpaid_only=True)
        if was_registered:
            freed[event.id] = event
    for event in sorted(freed.values(), key=lambda e: (e.date, e.start_time, e.id)):
        promote_waiting(db, now, actor, event)
    return cancelled


def on_member_deactivated(db: Session, now: datetime.datetime, actor: User, member_id: int) -> None:
    """LIB-EVT-40: fees stay."""
    release_member(db, now, actor, member_id, "member_deactivated", waive=False)
