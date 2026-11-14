"""Processing of events: no-shows, completion and reminders (LIB-EVT-33)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.events.bans import apply_no_show_ban
from lms.events.lifecycle import event_label, mark_cancelled
from lms.events.models import Event, EventRegistration
from lms.events.rules import REMINDER_WINDOW
from lms.notifications.service import event_reminder_sent, notify_event


def process(db: Session, now: datetime.datetime, actor: User) -> tuple[int, int, int, int]:
    """Returns ``(completed_events, no_shows, bans, reminders)``."""
    ended = [
        e
        for e in db.scalars(
            sa.select(Event)
            .where(Event.status == "published", Event.date <= now.date())
            .order_by(Event.date, Event.start_time, Event.id)
        )
        if e.end_at < now
    ]
    no_shows = 0
    members: list[int] = []
    for event in ended:
        event.status = "completed"
        registrations = db.scalars(
            sa.select(EventRegistration)
            .where(EventRegistration.event_id == event.id, EventRegistration.status.in_(("registered", "waitlisted")))
            .order_by(EventRegistration.id)
        ).all()
        for reg in registrations:
            if reg.status == "registered":
                reg.status = "no_show"
                no_shows += 1
                if reg.member_id not in members:
                    members.append(reg.member_id)
                record(
                    db,
                    at=now,
                    event="event_no_show",
                    actor_user_id=actor.id,
                    entity_type="event_registration",
                    entity_id=reg.id,
                    details={"event_id": event.id, "member_id": reg.member_id},
                )
            else:
                mark_cancelled(db, now, actor, reg, "event_cancelled")
    db.flush()

    bans = sum(1 for member_id in members if apply_no_show_ban(db, now, actor, member_id) is not None)

    reminders = 0
    soon = db.scalars(
        sa.select(Event)
        .where(
            Event.status == "published",
            Event.date >= now.date(),
            Event.date <= (now + REMINDER_WINDOW).date(),
        )
        .order_by(Event.date, Event.start_time, Event.id)
    ).all()
    for event in soon:
        if not now < event.start_at <= now + REMINDER_WINDOW:
            continue
        registrations = db.scalars(
            sa.select(EventRegistration)
            .where(EventRegistration.event_id == event.id, EventRegistration.status == "registered")
            .order_by(EventRegistration.id)
        ).all()
        for reg in registrations:
            if event_reminder_sent(db, reg.id):
                continue
            notify_event(
                db,
                now,
                reg.member_id,
                "event_reminder",
                f"Reminder: you are registered for {event_label(event)}.",
                event_id=event.id,
                event_registration_id=reg.id,
            )
            reminders += 1

    record(
        db,
        at=now,
        event="events_processed",
        actor_user_id=actor.id,
        entity_type="event",
        entity_id=None,
        details={"completed_events": len(ended), "no_shows": no_shows, "bans": bans, "reminders": reminders},
    )
    return len(ended), no_shows, bans, reminders
