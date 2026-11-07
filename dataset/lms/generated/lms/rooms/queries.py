"""Shared lookups of module 15: bookings of a day or week, bans in force, and the activity rules of 23.1/23.6."""

from __future__ import annotations

import datetime
from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.rooms.models import Room, RoomBan, RoomBooking, RoomBookingParticipant
from lms.rooms.rules import ACTIVE_STATUSES, NO_SHOW_GRACE, QUOTA_STATUSES


def is_due_no_show(booking: RoomBooking, now: datetime.datetime) -> bool:
    """LIB-ROOM-28: a ``booked`` booking more than 15 minutes past its start."""
    return booking.status == "booked" and now > booking.start_at + NO_SHOW_GRACE


def is_active(booking: RoomBooking, now: datetime.datetime) -> bool:
    """Active bookings are ``booked`` or ``checked_in``; a booking due as a no-show is not active (LIB-ROOM-28)."""
    return booking.status == "checked_in" or (booking.status == "booked" and not is_due_no_show(booking, now))


def involving(member_ids: Iterable[int]) -> sa.ColumnElement[bool]:
    """Bookings in which one of the members is a person (organizer or participant)."""
    ids = list(member_ids)
    return sa.or_(
        RoomBooking.member_id.in_(ids),
        RoomBooking.id.in_(
            sa.select(RoomBookingParticipant.booking_id).where(RoomBookingParticipant.member_id.in_(ids))
        ),
    )


def is_person(booking: RoomBooking, member_id: int) -> bool:
    return booking.member_id == member_id or member_id in booking.participant_ids


def bookings_on(db: Session, day: datetime.date, statuses: Iterable[str] = ACTIVE_STATUSES) -> list[RoomBooking]:
    stmt = sa.select(RoomBooking).where(RoomBooking.date == day, RoomBooking.status.in_(tuple(statuses)))
    return list(db.scalars(stmt.order_by(RoomBooking.date, RoomBooking.start_time, RoomBooking.id)))


def active_bookings_of_room(
    db: Session, room_id: int, day: datetime.date, now: datetime.datetime
) -> list[RoomBooking]:
    stmt = sa.select(RoomBooking).where(
        RoomBooking.room_id == room_id, RoomBooking.date == day, RoomBooking.status.in_(ACTIVE_STATUSES)
    )
    stmt = stmt.order_by(RoomBooking.start_time, RoomBooking.id)
    return [b for b in db.scalars(stmt) if is_active(b, now)]


def overlaps(a_start: datetime.time, a_end: datetime.time, b_start: datetime.time, b_end: datetime.time) -> bool:
    """LIB-ROOM-14: bookings that only touch do not overlap."""
    return a_start < b_end and b_start < a_end


def overlapping_active_of_members(
    db: Session,
    member_ids: Iterable[int],
    day: datetime.date,
    start: datetime.time,
    end: datetime.time,
    now: datetime.datetime,
    *,
    exclude_booking_id: int | None = None,
) -> list[RoomBooking]:
    stmt = sa.select(RoomBooking).where(
        RoomBooking.date == day, RoomBooking.status.in_(ACTIVE_STATUSES), involving(member_ids)
    )
    return [
        b
        for b in db.scalars(stmt)
        if b.id != exclude_booking_id and is_active(b, now) and overlaps(start, end, b.start_time, b.end_time)
    ]


def quota_minutes(db: Session, member_id: int, first: datetime.date, last: datetime.date) -> int:
    """Minutes of bookings that count for quota (23.1) in which the member is a person, dates inclusive."""
    stmt = sa.select(RoomBooking).where(
        RoomBooking.date >= first,
        RoomBooking.date <= last,
        RoomBooking.status.in_(QUOTA_STATUSES),
        involving([member_id]),
    )
    return sum(b.duration_minutes for b in db.scalars(stmt))


def future_organized_count(db: Session, member_id: int, now: datetime.datetime) -> int:
    """Active bookings with a start after now in which the member is the organizer."""
    stmt = sa.select(RoomBooking).where(
        RoomBooking.member_id == member_id,
        RoomBooking.status.in_(ACTIVE_STATUSES),
        RoomBooking.date >= now.date(),
    )
    return sum(1 for b in db.scalars(stmt) if b.start_at > now and is_active(b, now))


def bans_in_force(db: Session, member_id: int, *days: datetime.date) -> list[RoomBan]:
    """Bans of the member in force on at least one of ``days`` (LIB-ROOM-12 step 6)."""
    bans = db.scalars(sa.select(RoomBan).where(RoomBan.member_id == member_id, RoomBan.lifted_at.is_(None)))
    return [ban for ban in bans if any(ban.in_force_on(d) for d in days)]


def room_of(db: Session, booking: RoomBooking) -> Room:
    room = db.get(Room, booking.room_id)
    assert room is not None
    return room
