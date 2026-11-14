"""No-show bans (LIB-EVT-34 to LIB-EVT-37)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.events import queries
from lms.events.lifecycle import release_member
from lms.events.models import Event, EventBan, EventRegistration
from lms.events.rules import BAN_DAYS, BAN_NO_SHOWS, BAN_WINDOW_DAYS
from lms.notifications.service import notify_event


def count_no_shows(db: Session, member_id: int, today: datetime.date) -> int:
    """No-shows for events dated in the 90 days ending today; once a ban exists only events after the start
    of the latest ban count (LIB-EVT-34)."""
    first = today - datetime.timedelta(days=BAN_WINDOW_DAYS - 1)
    stmt = (
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
    latest = queries.latest_ban(db, member_id)
    if latest is not None:
        stmt = stmt.where(Event.date > latest.starts_on)
    return db.scalar(stmt) or 0


def apply_no_show_ban(db: Session, now: datetime.datetime, actor: User, member_id: int) -> EventBan | None:
    """LIB-EVT-34, LIB-EVT-35: called after a no-show."""
    today = now.date()
    if queries.bans_in_force(db, member_id, today):
        return None
    if count_no_shows(db, member_id, today) < BAN_NO_SHOWS:
        return None
    ban = EventBan(
        member_id=member_id, starts_on=today, ends_on=today + datetime.timedelta(days=BAN_DAYS - 1), created_at=now
    )
    db.add(ban)
    db.flush()
    record(
        db,
        at=now,
        event="event_ban_started",
        actor_user_id=actor.id,
        entity_type="event_ban",
        entity_id=ban.id,
        details={"member_id": member_id, "starts_on": ban.starts_on.isoformat(), "ends_on": ban.ends_on.isoformat()},
    )
    notify_event(
        db,
        now,
        member_id,
        "event_ban_started",
        f"You are banned from events from {ban.starts_on.isoformat()} to {ban.ends_on.isoformat()}.",
    )
    release_member(db, now, actor, member_id, "member_banned", first=ban.starts_on, last=ban.ends_on, waive=True)
    return ban
