"""Event attendance report (LIB-EVT-46) and the event figures of the member summary (LIB-EVT-39)."""

from __future__ import annotations

import datetime
from collections import defaultdict
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.money import ZERO, format_amount
from lms.events import queries
from lms.events.models import Event, EventRegistration
from lms.events.rules import BAN_WINDOW_DAYS
from lms.events.schemas import AttendanceOut, EventSummaryOut
from lms.fines.models import Fee


def member_summary(db: Session, now: datetime.datetime, member_id: int) -> EventSummaryOut:
    today = now.date()
    upcoming = queries.active_upcoming_registrations(db, member_id, now)
    first = today - datetime.timedelta(days=BAN_WINDOW_DAYS - 1)
    no_shows = db.scalar(
        sa.select(sa.func.count())
        .select_from(EventRegistration)
        .join(Event, Event.id == EventRegistration.event_id)
        .where(
            EventRegistration.member_id == member_id,
            EventRegistration.status == "no_show",
            Event.date >= first,
            Event.date <= today,
        )
    )
    bans = queries.bans_in_force(db, member_id, today)
    return EventSummaryOut(
        registered=sum(1 for r, _ in upcoming if r.status == "registered"),
        waitlisted=sum(1 for r, _ in upcoming if r.status == "waitlisted"),
        no_shows_90_days=no_shows or 0,
        banned_until=max(b.ends_on for b in bans) if bans else None,
    )


def attendance(
    db: Session,
    first: datetime.date,
    last: datetime.date,
    *,
    branch_id: int | None = None,
    kind: str | None = None,
) -> sa.Select[tuple[Event]]:
    stmt = (
        sa.select(Event)
        .where(Event.date >= first, Event.date <= last, Event.status != "draft")
        .order_by(Event.date, Event.start_time, Event.id)
    )
    if branch_id is not None:
        stmt = stmt.where(Event.branch_id == branch_id)
    if kind is not None:
        stmt = stmt.where(Event.kind == kind)
    return stmt


def attendance_out(db: Session, event: Event) -> AttendanceOut:
    counts: dict[str, int] = defaultdict(int)
    late = 0
    for reg in db.scalars(sa.select(EventRegistration).where(EventRegistration.event_id == event.id)):
        counts[reg.status] += 1
        if reg.late_cancellation:
            late += 1
    fees = db.scalars(
        sa.select(Fee)
        .join(EventRegistration, EventRegistration.id == Fee.event_registration_id)
        .where(EventRegistration.event_id == event.id, Fee.kind == "event_fee", Fee.status != "waived")
    )
    charged: Decimal = sum((f.amount for f in fees), ZERO)
    return AttendanceOut(
        event_id=event.id,
        title=event.title,
        kind=event.kind,
        date=event.date,
        status=event.status,
        capacity=event.capacity,
        registered=counts["registered"] + counts["attended"] + counts["no_show"],
        attended=counts["attended"],
        no_shows=counts["no_show"],
        late_cancellations=late,
        fees_charged=format_amount(charged),
    )
