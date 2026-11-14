"""Room bans (LIB-ROOM-31 to LIB-ROOM-36)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.core.errors import Conflict, NotFound
from lms.notifications.service import notify_room
from lms.rooms.lifecycle import release_member
from lms.rooms.models import RoomBan, RoomBooking
from lms.rooms.queries import bans_in_force
from lms.rooms.rules import (
    INCIDENT_BAN_DAYS,
    INCIDENT_BAN_THRESHOLD,
    INCIDENT_WINDOW_DAYS,
)


def get_ban_or_404(db: Session, ban_id: int) -> RoomBan:
    ban = db.get(RoomBan, ban_id)
    if ban is None:
        raise NotFound(f"Room ban {ban_id} does not exist", details={"resource": "room_ban", "id": ban_id})
    return ban


def create_ban(
    db: Session,
    now: datetime.datetime,
    actor_id: int | None,
    member_id: int,
    starts_on: datetime.date,
    ends_on: datetime.date,
    reason: str,
    note: str = "",
    *,
    created_by: int | None = None,
) -> RoomBan:
    """Create a ban, notify the member and apply LIB-ROOM-33. ``created_by`` is null for system bans."""
    ban = RoomBan(
        member_id=member_id,
        starts_on=starts_on,
        ends_on=ends_on,
        reason=reason,
        note=note,
        created_at=now,
        created_by=created_by,
    )
    db.add(ban)
    db.flush()
    record(
        db,
        at=now,
        event="room_ban_started",
        actor_user_id=actor_id,
        entity_type="room_ban",
        entity_id=ban.id,
        details={
            "member_id": member_id,
            "starts_on": starts_on.isoformat(),
            "ends_on": ends_on.isoformat(),
            "reason": reason,
            "note": note,
        },
    )
    notify_room(
        db,
        now,
        member_id,
        "room_ban_started",
        f"You are banned from booking study rooms from {starts_on.isoformat()} to {ends_on.isoformat()}.",
    )
    release_member(db, now, actor_id, member_id, "member_banned", first=starts_on, last=ends_on)
    return ban


def count_incidents(db: Session, member_id: int, today: datetime.date) -> int:
    """LIB-ROOM-31: no-shows and late cancellations of bookings the member organized, dated in the 30 days ending
    today, that closed after the latest ``no_shows`` ban was created."""
    last_ban = db.scalar(
        sa.select(RoomBan)
        .where(RoomBan.member_id == member_id, RoomBan.reason == "no_shows")
        .order_by(RoomBan.created_at.desc(), RoomBan.id.desc())
        .limit(1)
    )
    first = today - datetime.timedelta(days=INCIDENT_WINDOW_DAYS - 1)
    stmt = sa.select(RoomBooking).where(
        RoomBooking.member_id == member_id,
        RoomBooking.date >= first,
        RoomBooking.date <= today,
        sa.or_(
            RoomBooking.status == "no_show",
            sa.and_(RoomBooking.status == "cancelled", RoomBooking.late_cancellation.is_(True)),
        ),
    )
    count = 0
    for booking in db.scalars(stmt):
        if last_ban is not None and not (booking.closed_at is not None and booking.closed_at > last_ban.created_at):
            continue
        count += 1
    return count


def apply_incident_ban(db: Session, now: datetime.datetime, actor_id: int | None, member_id: int) -> RoomBan | None:
    """LIB-ROOM-31: called after a no-show or a late cancellation."""
    today = now.date()
    if bans_in_force(db, member_id, today):
        return None
    if count_incidents(db, member_id, today) < INCIDENT_BAN_THRESHOLD:
        return None
    ends_on = today + datetime.timedelta(days=INCIDENT_BAN_DAYS - 1)
    return create_ban(db, now, actor_id, member_id, today, ends_on, "no_shows")


def lift_ban(db: Session, now: datetime.datetime, actor: User, ban: RoomBan) -> RoomBan:
    """LIB-ROOM-35."""
    if ban.lifted_at is not None or ban.ends_on < now.date():
        raise Conflict("The ban is not active", code="BAN_NOT_ACTIVE", details={"id": ban.id})
    ban.lifted_at = now
    ban.lifted_by = actor.id
    record(
        db,
        at=now,
        event="room_ban_lifted",
        actor_user_id=actor.id,
        entity_type="room_ban",
        entity_id=ban.id,
        details={"member_id": ban.member_id},
    )
    return ban
