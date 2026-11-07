"""Cancellations, removal of participants and their effects on a member's bookings (LIB-ROOM-21, 26, 33, 37, 38)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.notifications.service import notify_room
from lms.rooms.models import Room, RoomBooking
from lms.rooms.queries import involving, is_due_no_show, room_of
from lms.rooms.rules import SYSTEM_CANCEL_REASONS
from lms.rooms.schemas import format_time


def booking_label(room: Room, booking: RoomBooking) -> str:
    """The room code, the date and the start time, as in the notifications of LIB-ROOM-41."""
    return f"{room.code} on {booking.date.isoformat()} at {format_time(booking.start_time)}"


def notify_persons(
    db: Session, now: datetime.datetime, booking: RoomBooking, type_: str, message: str, member_ids: list[int] | None = None
) -> None:
    for member_id in booking.person_ids if member_ids is None else member_ids:
        notify_room(db, now, member_id, type_, message, room_booking_id=booking.id)


def cancel_booking(
    db: Session,
    now: datetime.datetime,
    actor_id: int | None,
    booking: RoomBooking,
    reason: str,
    *,
    late: bool = False,
) -> None:
    """Set a booking to ``cancelled``; system reasons notify every person (LIB-ROOM-26)."""
    room = room_of(db, booking)
    booking.status = "cancelled"
    booking.closed_at = now
    booking.cancel_reason = reason
    booking.late_cancellation = late
    record(
        db,
        at=now,
        event="room_booking_cancelled",
        actor_user_id=actor_id,
        entity_type="room_booking",
        entity_id=booking.id,
        details={"reason": reason, "late_cancellation": late, "room_id": room.id, "date": booking.date.isoformat()},
    )
    if reason in SYSTEM_CANCEL_REASONS:
        message = f"Your room booking for {booking_label(room, booking)} was cancelled ({reason})."
        notify_persons(db, now, booking, "room_booking_cancelled", message)


def remove_participant(
    db: Session, now: datetime.datetime, actor_id: int | None, booking: RoomBooking, member_id: int
) -> None:
    """LIB-ROOM-21: remove a participant; too few remaining persons cancel the booking."""
    booking.participants = [p for p in booking.participants if p.member_id != member_id]
    record(
        db,
        at=now,
        event="room_participant_left",
        actor_user_id=actor_id,
        entity_type="room_booking",
        entity_id=booking.id,
        details={"member_id": member_id},
    )
    db.flush()
    room = room_of(db, booking)
    if len(booking.person_ids) < room.min_participants:
        cancel_booking(db, now, actor_id, booking, "not_enough_participants")


def _booked_bookings(db: Session, *conditions: sa.ColumnElement[bool]) -> list[RoomBooking]:
    stmt = (
        sa.select(RoomBooking)
        .where(RoomBooking.status == "booked", *conditions)
        .order_by(RoomBooking.date, RoomBooking.start_time, RoomBooking.id)
    )
    return list(db.scalars(stmt))


def release_member(
    db: Session,
    now: datetime.datetime,
    actor_id: int | None,
    member_id: int,
    reason: str,
    *,
    future_only: bool = False,
    first: datetime.date | None = None,
    last: datetime.date | None = None,
) -> None:
    """Cancel the ``booked`` bookings the member organizes and remove them from the ``booked`` group bookings they
    take part in (LIB-ROOM-33, 37, 38), optionally only for dates in ``first``..``last``.

    A booking that is due as a no-show is left to the no-show processing (LIB-ROOM-28); with ``future_only`` only
    bookings that start after now are touched."""
    date_filter: list[sa.ColumnElement[bool]] = []
    if first is not None:
        date_filter.append(RoomBooking.date >= first)
    if last is not None:
        date_filter.append(RoomBooking.date <= last)

    def eligible(booking: RoomBooking) -> bool:
        if future_only:
            return booking.start_at > now
        return not is_due_no_show(booking, now)

    for booking in _booked_bookings(db, RoomBooking.member_id == member_id, *date_filter):
        if eligible(booking):
            cancel_booking(db, now, actor_id, booking, reason)
    for booking in _booked_bookings(db, RoomBooking.member_id != member_id, involving([member_id]), *date_filter):
        if member_id in booking.participant_ids and eligible(booking):
            remove_participant(db, now, actor_id, booking, member_id)


def is_in_checked_in_room(db: Session, member_id: int) -> bool:
    """LIB-ROOM-37: the member is a person of a ``checked_in`` booking."""
    stmt = sa.select(RoomBooking.id).where(RoomBooking.status == "checked_in", involving([member_id])).limit(1)
    return db.scalar(stmt) is not None


def on_member_deactivated(db: Session, now: datetime.datetime, actor_id: int | None, member_id: int) -> None:
    """LIB-ROOM-37."""
    release_member(db, now, actor_id, member_id, "member_deactivated")


def on_member_became_guest(db: Session, now: datetime.datetime, actor_id: int | None, member_id: int) -> None:
    """LIB-ROOM-38: future bookings are cancelled with reason ``staff_request``."""
    release_member(db, now, actor_id, member_id, "staff_request", future_only=True)
