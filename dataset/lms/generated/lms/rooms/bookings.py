"""Room bookings (LIB-ROOM-10 to LIB-ROOM-30, LIB-ROOM-42)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.calendar import add_working_days, is_working_day
from lms.core.clock import LOCAL_TZ
from lms.core.errors import Conflict, NotFound, ValidationFailed, reference_not_found
from lms.core.money import format_amount
from lms.fines import service as fines
from lms.members.models import Member
from lms.notifications.service import notify_room, room_reminder_sent
from lms.rooms.bans import apply_incident_ban
from lms.rooms.lifecycle import booking_label, cancel_booking, remove_participant
from lms.rooms.models import Room, RoomBooking, RoomBookingParticipant
from lms.rooms.queries import (
    active_bookings_of_room,
    bans_in_force,
    future_organized_count,
    involving,
    is_due_no_show,
    overlapping_active_of_members,
    quota_minutes,
    room_of,
)
from lms.rooms.rules import (
    CHECK_IN_EARLY,
    DEBT_BLOCK,
    LATE_CANCELLATION_WINDOW,
    NO_SHOW_FEE,
    NO_SHOW_GRACE,
    ROOM_RULES,
    format_hours,
    minutes_between,
    week_start,
)
from lms.rooms.schemas import format_time
from lms.staff.schedule import has_closure_on

_HALF_HOUR = datetime.timedelta(minutes=30)


def get_booking_or_404(db: Session, booking_id: int) -> RoomBooking:
    booking = db.get(RoomBooking, booking_id)
    if booking is None:
        raise NotFound(
            f"Room booking {booking_id} does not exist", details={"resource": "room_booking", "id": booking_id}
        )
    return booking


def _member_or_404(db: Session, field: str, member_id: int) -> Member:
    member = db.get(Member, member_id)
    if member is None:
        raise reference_not_found(field, member_id)
    return member


def _participants_or_404(db: Session, participant_ids: list[int]) -> list[Member]:
    return [_member_or_404(db, "participant_ids", pid) for pid in participant_ids]


def _error(code: str, message: str, **details: Any) -> Conflict:
    return Conflict(message, code=code, details=details)


# --- checks of LIB-ROOM-12 ---------------------------------------------------------------


def _total_debt(db: Session, member_id: int, now: datetime.datetime, holidays: Container[datetime.date]):  # noqa: ANN202
    return fines.outstanding_fees(db, member_id) + fines.accrued_late_fees(db, member_id, now, holidays)


def _check_organizer(
    db: Session,
    organizer: Member,
    now: datetime.datetime,
    day: datetime.date,
    holidays: Container[datetime.date],
) -> None:
    """Steps (3) to (7)."""
    if organizer.status == "passive":
        raise _error("MEMBER_PASSIVE", "The member is passive")
    if day > organizer.valid_until:
        raise _error("MEMBERSHIP_EXPIRED", "The membership is not valid on the booking date")
    if organizer.membership_type == "guest":
        raise _error("ROOM_NOT_ALLOWED_FOR_TYPE", "Guests cannot book study rooms")
    bans = bans_in_force(db, organizer.id, now.date(), day)
    if bans:
        raise _error(
            "MEMBER_BANNED_FROM_ROOMS",
            "The member is banned from study rooms",
            ends_on=max(b.ends_on for b in bans).isoformat(),
        )
    debt = _total_debt(db, organizer.id, now, holidays)
    if debt >= DEBT_BLOCK:
        raise _error("MEMBER_BLOCKED_BY_DEBT", "The member's debt blocks bookings", total_debt=format_amount(debt))


def _eligibility_problem(db: Session, member: Member, day: datetime.date) -> str | None:
    """LIB-ROOM-13 (e): the code that applies to a participant, if any."""
    if member.status == "passive":
        return "MEMBER_PASSIVE"
    if member.membership_type == "guest":
        return "ROOM_NOT_ALLOWED_FOR_TYPE"
    if day > member.valid_until:
        return "MEMBERSHIP_EXPIRED"
    if bans_in_force(db, member.id, day):
        return "MEMBER_BANNED_FROM_ROOMS"
    return None


def _check_participants(db: Session, room: Room, organizer_id: int, participants: list[Member], day: datetime.date) -> None:
    """LIB-ROOM-13 (a), (c), (d), (e); (b) is the existence check done before."""
    if room.kind == "individual" and participants:
        raise _error("PARTICIPANTS_NOT_ALLOWED", "An individual room cannot have participants")
    persons = 1 + len(participants)
    if persons < room.min_participants:
        raise _error(
            "NOT_ENOUGH_PARTICIPANTS", "Not enough participants", min_participants=room.min_participants
        )
    if persons > room.capacity:
        raise _error("ROOM_CAPACITY_EXCEEDED", "The room capacity is exceeded", capacity=room.capacity)
    for member in sorted(participants, key=lambda m: m.id):
        problem = _eligibility_problem(db, member, day)
        if problem is not None:
            raise _error(
                "PARTICIPANT_NOT_ELIGIBLE",
                "A participant is not eligible",
                member_id=member.id,
                reason=problem,
            )


def _check_double_booking(
    db: Session,
    now: datetime.datetime,
    member_ids: list[int],
    day: datetime.date,
    start: datetime.time,
    end: datetime.time,
    exclude_booking_id: int | None = None,
) -> None:
    """Step (14): the smallest member id that has another overlapping active booking."""
    if not member_ids:
        return
    clashing = overlapping_active_of_members(db, member_ids, day, start, end, now, exclude_booking_id=exclude_booking_id)
    busy = {m for b in clashing for m in b.person_ids}
    candidates = sorted(m for m in member_ids if m in busy)
    if candidates:
        raise _error("MEMBER_DOUBLE_BOOKED", "A person already has an overlapping booking", member_id=candidates[0])


def _check_quotas(
    db: Session,
    now: datetime.datetime,
    persons: list[Member],
    organizer_id: int | None,
    day: datetime.date,
    minutes: int,
) -> None:
    """LIB-ROOM-15 with the new booking included; ``organizer_id`` is None when no organizer is checked."""
    first = week_start(day)
    last = first + datetime.timedelta(days=6)
    for member in sorted(persons, key=lambda m: m.id):
        rules = ROOM_RULES[member.membership_type]
        used_day = quota_minutes(db, member.id, day, day) + minutes
        if used_day > rules.daily_hours * 60:
            raise _error(
                "DAILY_ROOM_QUOTA_EXCEEDED",
                "The daily room quota is exceeded",
                member_id=member.id,
                limit=format_hours(rules.daily_hours * 60),
                used=format_hours(used_day),
            )
        used_week = quota_minutes(db, member.id, first, last) + minutes
        if used_week > rules.weekly_hours * 60:
            raise _error(
                "WEEKLY_ROOM_QUOTA_EXCEEDED",
                "The weekly room quota is exceeded",
                member_id=member.id,
                limit=format_hours(rules.weekly_hours * 60),
                used=format_hours(used_week),
            )
        if member.id == organizer_id:
            used_count = future_organized_count(db, member.id, now) + 1
            if used_count > rules.future_limit:
                raise _error(
                    "ROOM_BOOKING_LIMIT_REACHED",
                    "The limit of active future bookings is reached",
                    member_id=member.id,
                    limit=rules.future_limit,
                    used=used_count,
                )


def _notify_added(db: Session, now: datetime.datetime, booking: RoomBooking, room: Room, member_ids: list[int]) -> None:
    message = f"You were added to a room booking for {booking_label(room, booking)}."
    for member_id in member_ids:
        notify_room(db, now, member_id, "room_participant_added", message, room_booking_id=booking.id)


# --- create, change ------------------------------------------------------------------------


def create_booking(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    actor: User,
    *,
    room_id: int,
    organizer_id: int,
    day: datetime.date,
    start: datetime.time,
    end: datetime.time,
    participant_ids: list[int],
    purpose: str,
) -> RoomBooking:
    """LIB-ROOM-10 to LIB-ROOM-17."""
    room = db.get(Room, room_id)
    if room is None:
        raise reference_not_found("room_id", room_id)
    organizer = _member_or_404(db, "member_id", organizer_id)
    participants = _participants_or_404(db, participant_ids)

    today = now.date()
    branch = db.get(Branch, room.branch_id)
    assert branch is not None
    if not branch.is_active:
        raise _error("BRANCH_INACTIVE", f"Branch {branch.code} is inactive", id=branch.id)
    if not room.is_active:
        raise _error("ROOM_INACTIVE", "The room is inactive", id=room.id)
    _check_organizer(db, organizer, now, day, holidays)
    if not is_working_day(day, holidays) or has_closure_on(db, branch.id, day):
        raise _error("ROOM_CLOSED", "The library is closed on this date")
    if start < room.opens_at or end > room.closes_at:
        raise _error(
            "OUTSIDE_ROOM_HOURS",
            "The interval is outside the opening hours of the room",
            opens_at=format_time(room.opens_at),
            closes_at=format_time(room.closes_at),
        )
    if datetime.datetime.combine(day, start, LOCAL_TZ) <= now:
        raise _error("BOOKING_IN_PAST", "The booking starts in the past")
    ahead = ROOM_RULES[organizer.membership_type].ahead_days
    assert ahead is not None
    latest = today + datetime.timedelta(days=ahead)
    if day > latest:
        raise _error("BOOKING_TOO_FAR_AHEAD", "The date is too far ahead", latest_date=latest.isoformat())
    _check_participants(db, room, organizer.id, participants, day)
    for other in active_bookings_of_room(db, room.id, day, now):
        if other.start_time < end and start < other.end_time:
            raise _error("ROOM_ALREADY_BOOKED", "The room is already booked", booking_id=other.id)
    persons = [organizer, *participants]
    _check_double_booking(db, now, [m.id for m in persons], day, start, end)
    _check_quotas(db, now, persons, organizer.id, day, minutes_between(start, end))

    booking = RoomBooking(
        room_id=room.id,
        member_id=organizer.id,
        date=day,
        start_time=start,
        end_time=end,
        status="booked",
        purpose=purpose,
        created_at=now,
        created_by=actor.id,
        participants=[RoomBookingParticipant(member_id=p.id) for p in participants],
    )
    db.add(booking)
    db.flush()
    record(
        db,
        at=now,
        event="room_booking_created",
        actor_user_id=actor.id,
        entity_type="room_booking",
        entity_id=booking.id,
        details={
            "room_id": room.id,
            "member_id": organizer.id,
            "participant_ids": booking.participant_ids,
            "date": day.isoformat(),
            "start_time": format_time(start),
            "end_time": format_time(end),
            "purpose": purpose,
        },
    )
    _notify_added(db, now, booking, room, booking.participant_ids)
    return booking


def update_booking(
    db: Session, now: datetime.datetime, actor: User, booking: RoomBooking, fields: dict[str, Any]
) -> RoomBooking:
    """LIB-ROOM-20."""
    new_ids: list[int] | None = fields.get("participant_ids")
    if new_ids is not None and booking.member_id in new_ids:
        raise ValidationFailed.single("participant_ids", "the organizer cannot be a participant")
    members = _participants_or_404(db, new_ids) if new_ids is not None else []
    if booking.status != "booked" or booking.start_at <= now:
        raise _error("BOOKING_NOT_CHANGEABLE", "The booking cannot be changed", status=booking.status)

    room = room_of(db, booking)
    old = {"participant_ids": booking.participant_ids, "purpose": booking.purpose}
    added: list[int] = []
    if new_ids is not None:
        organizer = db.get(Member, booking.member_id)
        assert organizer is not None
        _check_participants(db, room, organizer.id, members, booking.date)
        added = sorted(set(new_ids) - set(booking.participant_ids))
        if added:
            added_members = [m for m in members if m.id in added]
            _check_double_booking(
                db, now, added, booking.date, booking.start_time, booking.end_time, exclude_booking_id=booking.id
            )
            _check_quotas(db, now, added_members, None, booking.date, booking.duration_minutes)
        keep = set(new_ids)
        booking.participants = [p for p in booking.participants if p.member_id in keep] + [
            RoomBookingParticipant(member_id=m) for m in added
        ]
    if "purpose" in fields and fields["purpose"] is not None:
        booking.purpose = fields["purpose"]
    db.flush()
    diff = changes(old, {"participant_ids": booking.participant_ids, "purpose": booking.purpose})
    if diff:
        record(
            db,
            at=now,
            event="room_booking_updated",
            actor_user_id=actor.id,
            entity_type="room_booking",
            entity_id=booking.id,
            details=diff,
        )
    _notify_added(db, now, booking, room, added)
    return booking


def leave_booking(db: Session, now: datetime.datetime, actor: User, booking: RoomBooking, member_id: int) -> RoomBooking:
    """LIB-ROOM-21; the caller has checked that the member is a participant."""
    if booking.status != "booked" or booking.start_at <= now:
        raise _error("BOOKING_NOT_CHANGEABLE", "The booking cannot be changed", status=booking.status)
    remove_participant(db, now, actor.id, booking, member_id)
    return booking


# --- cancel, check-in, check-out -----------------------------------------------------------


def cancel(db: Session, now: datetime.datetime, actor: User, booking: RoomBooking, *, by_organizer: bool) -> RoomBooking:
    """LIB-ROOM-22 to LIB-ROOM-25."""
    if booking.status != "booked" or is_due_no_show(booking, now):
        raise _error("BOOKING_NOT_ACTIVE", "The booking is not active", status=booking.status)
    late = by_organizer and booking.start_at - now < LATE_CANCELLATION_WINDOW
    cancel_booking(db, now, actor.id, booking, "member_request" if by_organizer else "staff_request", late=late)
    if late:
        apply_incident_ban(db, now, actor.id, booking.member_id)
    return booking


def check_in(db: Session, now: datetime.datetime, actor: User, booking: RoomBooking) -> RoomBooking:
    """LIB-ROOM-27."""
    if booking.status != "booked":
        raise _error("BOOKING_NOT_ACTIVE", "The booking is not active", status=booking.status)
    earliest = booking.start_at - CHECK_IN_EARLY
    if now < earliest:
        raise _error(
            "CHECK_IN_TOO_EARLY",
            "Check-in is not open yet",
            earliest=earliest.astimezone(LOCAL_TZ).isoformat(),
        )
    if now > booking.start_at + NO_SHOW_GRACE:
        raise _error("CHECK_IN_TOO_LATE", "The booking is due as a no-show")
    booking.status = "checked_in"
    booking.checked_in_at = now
    record(
        db,
        at=now,
        event="room_checked_in",
        actor_user_id=actor.id,
        entity_type="room_booking",
        entity_id=booking.id,
        details={"member_id": booking.member_id},
    )
    return booking


def _round_up_half_hour(moment: datetime.datetime) -> datetime.datetime:
    base = moment.replace(minute=0, second=0, microsecond=0)
    elapsed = moment - base
    steps = -(-elapsed // _HALF_HOUR)  # ceiling division of timedeltas
    return base + steps * _HALF_HOUR


def check_out(db: Session, now: datetime.datetime, actor: User, booking: RoomBooking) -> RoomBooking:
    """LIB-ROOM-29."""
    if booking.status != "checked_in":
        raise _error("BOOKING_NOT_ACTIVE", "The booking is not checked in", status=booking.status)
    old_end = booking.end_at
    new_end = min(max(_round_up_half_hour(now), booking.start_at + _HALF_HOUR), old_end)
    booking.end_time = new_end.timetz().replace(tzinfo=None)
    booking.status = "completed"
    booking.closed_at = now
    record(
        db,
        at=now,
        event="room_checked_out",
        actor_user_id=actor.id,
        entity_type="room_booking",
        entity_id=booking.id,
        details={"end_time": {"old": format_time(old_end.time()), "new": format_time(booking.end_time)}},
    )
    return booking


# --- processing, reminders -----------------------------------------------------------------


def process(db: Session, now: datetime.datetime, actor: User) -> tuple[int, int, int]:
    """LIB-ROOM-28, LIB-ROOM-30, LIB-ROOM-31: returns ``(no_shows, completed, bans)``."""
    order = (RoomBooking.date, RoomBooking.start_time, RoomBooking.id)
    candidates = db.scalars(
        sa.select(RoomBooking)
        .where(RoomBooking.status == "booked", RoomBooking.date <= now.date())
        .order_by(*order)
    ).all()
    no_shows = bans = 0
    for booking in candidates:
        if booking.status != "booked" or not is_due_no_show(booking, now):
            continue
        room = room_of(db, booking)
        booking.status = "no_show"
        booking.closed_at = now
        no_shows += 1
        record(
            db,
            at=now,
            event="room_no_show",
            actor_user_id=actor.id,
            entity_type="room_booking",
            entity_id=booking.id,
            details={"member_id": booking.member_id, "room_id": room.id, "date": booking.date.isoformat()},
        )
        notify_room(
            db,
            now,
            booking.member_id,
            "room_no_show",
            f"You did not show up for your room booking for {booking_label(room, booking)}.",
            room_booking_id=booking.id,
        )
        fines.create_fee(
            db,
            now,
            actor,
            member_id=booking.member_id,
            loan_id=None,
            kind="no_show_fee",
            amount=NO_SHOW_FEE,
            room_booking_id=booking.id,
        )
        if apply_incident_ban(db, now, actor.id, booking.member_id) is not None:
            bans += 1

    completed = 0
    checked_in = db.scalars(
        sa.select(RoomBooking)
        .where(RoomBooking.status == "checked_in", RoomBooking.date <= now.date())
        .order_by(*order)
    ).all()
    for booking in checked_in:
        if now < booking.end_at:
            continue
        booking.status = "completed"
        booking.closed_at = now
        completed += 1
        record(
            db,
            at=now,
            event="room_booking_completed",
            actor_user_id=actor.id,
            entity_type="room_booking",
            entity_id=booking.id,
            details={"member_id": booking.member_id},
        )
    record(
        db,
        at=now,
        event="room_bookings_processed",
        actor_user_id=actor.id,
        entity_type="room_booking",
        entity_id=None,
        details={"no_shows": no_shows, "completed": completed, "bans": bans},
    )
    return no_shows, completed, bans


def run_reminders(db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date]) -> int:
    """LIB-ROOM-42."""
    next_day = add_working_days(now.date(), 1, holidays)
    bookings = db.scalars(
        sa.select(RoomBooking)
        .where(RoomBooking.status == "booked", RoomBooking.date == next_day)
        .order_by(RoomBooking.date, RoomBooking.start_time, RoomBooking.id)
    ).all()
    count = 0
    for booking in bookings:
        room = room_of(db, booking)
        message = f"Reminder: you have a room booking for {booking_label(room, booking)}."
        for member_id in booking.person_ids:
            if room_reminder_sent(db, booking.id, member_id):
                continue
            notify_room(db, now, member_id, "room_reminder", message, room_booking_id=booking.id)
            count += 1
    record(
        db,
        at=now,
        event="room_reminders_run",
        actor_user_id=actor.id,
        entity_type="room_booking",
        entity_id=None,
        details={"room_reminders": count},
    )
    return count


# --- lists ------------------------------------------------------------------------------------


def booking_list_stmt(
    *,
    person_id: int | None = None,
    status: str | None = None,
    room_id: int | None = None,
    branch_id: int | None = None,
    first: datetime.date | None = None,
    last: datetime.date | None = None,
) -> sa.Select[tuple[RoomBooking]]:
    """LIB-ROOM-18."""
    stmt = sa.select(RoomBooking).order_by(RoomBooking.date, RoomBooking.start_time, RoomBooking.id)
    if person_id is not None:
        stmt = stmt.where(involving([person_id]))
    if status is not None:
        stmt = stmt.where(RoomBooking.status == status)
    if room_id is not None:
        stmt = stmt.where(RoomBooking.room_id == room_id)
    if branch_id is not None:
        stmt = stmt.where(RoomBooking.room_id.in_(sa.select(Room.id).where(Room.branch_id == branch_id)))
    if first is not None:
        stmt = stmt.where(RoomBooking.date >= first)
    if last is not None:
        stmt = stmt.where(RoomBooking.date <= last)
    return stmt
