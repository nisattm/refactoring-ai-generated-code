"""Room usage report (LIB-ROOM-44) and the room figures of the member summary (LIB-ROOM-40)."""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Container
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.calendar import is_working_day
from lms.rooms.models import Room, RoomBooking
from lms.rooms.queries import bans_in_force, involving, is_active, quota_minutes
from lms.rooms.rules import ACTIVE_STATUSES, format_hours, minutes_between, week_start
from lms.rooms.schemas import RoomSummaryOut, RoomUsageOut


def member_summary(db: Session, now: datetime.datetime, member_id: int) -> RoomSummaryOut:
    today = now.date()
    stmt = sa.select(RoomBooking).where(
        RoomBooking.status.in_(ACTIVE_STATUSES), RoomBooking.date >= today, involving([member_id])
    )
    upcoming = sum(1 for b in db.scalars(stmt) if b.start_at > now and is_active(b, now))
    bans = bans_in_force(db, member_id, today)
    first = week_start(today)
    minutes = quota_minutes(db, member_id, first, first + datetime.timedelta(days=6))
    return RoomSummaryOut(
        upcoming_bookings=upcoming,
        banned_until=max(b.ends_on for b in bans).isoformat() if bans else None,
        hours_this_week=format_hours(minutes),
    )


def _percent(used: int, open_: int) -> str:
    if open_ == 0:
        return "0.0"
    value = (Decimal(used) * 100 / Decimal(open_)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(value, "f")


def room_usage(
    db: Session,
    first: datetime.date,
    last: datetime.date,
    holidays: Container[datetime.date],
    *,
    branch_id: int | None = None,
    kind: str | None = None,
) -> list[RoomUsageOut]:
    """One item per room, ordered by branch and code."""
    stmt = sa.select(Room).order_by(Room.branch_id, Room.code, Room.id)
    if branch_id is not None:
        stmt = stmt.where(Room.branch_id == branch_id)
    if kind is not None:
        stmt = stmt.where(Room.kind == kind)
    rooms = list(db.scalars(stmt))
    working_days = sum(
        1 for offset in range((last - first).days + 1) if is_working_day(first + datetime.timedelta(days=offset), holidays)
    )

    booked: dict[int, int] = defaultdict(int)
    used: dict[int, int] = defaultdict(int)
    no_shows: dict[int, int] = defaultdict(int)
    late: dict[int, int] = defaultdict(int)
    bookings = db.scalars(sa.select(RoomBooking).where(RoomBooking.date >= first, RoomBooking.date <= last))
    for booking in bookings:
        if booking.status in ("checked_in", "completed", "no_show"):
            booked[booking.room_id] += booking.duration_minutes
        if booking.status in ("checked_in", "completed"):
            used[booking.room_id] += booking.duration_minutes
        if booking.status == "no_show":
            no_shows[booking.room_id] += 1
        if booking.status == "cancelled" and booking.late_cancellation:
            late[booking.room_id] += 1

    items = []
    for room in rooms:
        open_minutes = working_days * minutes_between(room.opens_at, room.closes_at)
        items.append(
            RoomUsageOut(
                room_id=room.id,
                room_code=room.code,
                branch_id=room.branch_id,
                open_hours=format_hours(open_minutes),
                booked_hours=format_hours(booked[room.id]),
                used_hours=format_hours(used[room.id]),
                no_shows=no_shows[room.id],
                late_cancellations=late[room.id],
                utilization=_percent(used[room.id], open_minutes),
            )
        )
    return items
