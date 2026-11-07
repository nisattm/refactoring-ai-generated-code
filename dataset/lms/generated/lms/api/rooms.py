"""Study room endpoints (section 23.3)."""

from __future__ import annotations

import datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.orm import Session

from lms.auth.deps import AdminOnly, AnyUser, CurrentPrincipal, Principal, StaffOnly, require_roles
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, ValidationFailed
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.core.timeutil import parse_date
from lms.members.models import Member
from lms.members.service import get_member_or_404
from lms.rooms import bans, bookings, rooms
from lms.rooms.models import RoomBan, RoomBooking
from lms.rooms.queries import is_person, room_of
from lms.rooms.schemas import (
    FEATURES,
    AvailabilityOut,
    BookingStatus,
    ProcessOut,
    RoomBanCreateIn,
    RoomBanOut,
    RoomBookingCreateIn,
    RoomBookingOut,
    RoomBookingPatchIn,
    RoomCreateIn,
    RoomKind,
    RoomOut,
    RoomPatchIn,
    RoomRemindersOut,
    ban_out,
    booking_out,
    parse_time,
    room_out,
)

router = APIRouter(tags=["rooms"])

RoomId = Annotated[int, Path(ge=1)]
BookingId = Annotated[int, Path(ge=1)]
BanId = Annotated[int, Path(ge=1)]
MemberId = Annotated[int, Path(ge=1)]
MemberOnly = Annotated[Principal, Depends(require_roles("member"))]


def _query_date(name: str, raw: str | None, problems: list[dict[str, str]]) -> datetime.date | None:
    if raw is None:
        problems.append({"field": name, "problem": "field required"})
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        problems.append({"field": name, "problem": "expected a valid date in the form YYYY-MM-DD"})
        return None


def _optional_date(name: str, raw: str | None) -> datetime.date | None:
    if raw is None:
        return None
    problems: list[dict[str, str]] = []
    value = _query_date(name, raw, problems)
    if problems:
        raise ValidationFailed(problems)
    return value


def _query_time(name: str, raw: str | None, problems: list[dict[str, str]]) -> datetime.time | None:
    if raw is None:
        problems.append({"field": name, "problem": "field required"})
        return None
    try:
        return parse_time(raw.strip())
    except ValueError as exc:
        problems.append({"field": name, "problem": str(exc)})
        return None


def _features(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    unknown = [v for v in values if v not in FEATURES]
    if unknown:
        raise ValidationFailed.single("feature", f"unknown feature {unknown[0]!r}")
    return values


def _is_staff(principal: Principal) -> bool:
    return principal.user.role != "member"


def _own_member_id(principal: Principal) -> int:
    member_id = principal.user.member_id
    if member_id is None:
        raise Forbidden("The authenticated user has no member record")
    return member_id


def _own_or_staff(principal: Principal, member_id: int) -> None:
    """LIB-AUTH-25."""
    if principal.user.role == "member" and principal.user.member_id != member_id:
        raise Forbidden("Only your own bookings and bans can be accessed")


def _require_organizer(principal: Principal, booking: RoomBooking) -> bool:
    """Members must be the organizer (LIB-AUTH-25); returns whether the acting user is the organizer."""
    if principal.user.role == "member":
        if principal.user.member_id != booking.member_id:
            raise Forbidden("Only the organizer can do this")
        return True
    return False


def _booking_out(db: Session, booking: RoomBooking) -> RoomBookingOut:
    return booking_out(booking, room_of(db, booking))


# --- rooms -----------------------------------------------------------------------------------


@router.post("/rooms", response_model=RoomOut, status_code=201)
def create_room(body: RoomCreateIn, request: Request, db: SessionDep, admin: AdminOnly) -> RoomOut:
    now = local_now(request.app.state.settings.clock)
    room = rooms.create_room(db, now, admin.user, **body.model_dump())
    return room_out(room)


@router.get("/rooms", response_model=Page[RoomOut])
def list_rooms(
    db: SessionDep,
    _: AnyUser,
    page: PageDep,
    branch_id: Annotated[int | None, Query()] = None,
    kind: Annotated[RoomKind | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    min_capacity: Annotated[int | None, Query()] = None,
    feature: Annotated[list[str] | None, Query()] = None,
) -> Page[RoomOut]:
    features = _features(feature)
    found = rooms.filter_rooms(
        db, branch_id=branch_id, kind=kind, is_active=is_active, min_capacity=min_capacity, features=features
    )
    return paginate_sequence([room_out(r) for r in found], page)


@router.get("/rooms/free", response_model=Page[RoomOut])
def free_rooms(
    request: Request,
    db: SessionDep,
    _: AnyUser,
    page: PageDep,
    date: Annotated[str | None, Query()] = None,
    start_time: Annotated[str | None, Query()] = None,
    end_time: Annotated[str | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    kind: Annotated[RoomKind | None, Query()] = None,
    min_capacity: Annotated[int | None, Query()] = None,
    feature: Annotated[list[str] | None, Query()] = None,
) -> Page[RoomOut]:
    settings = request.app.state.settings
    problems: list[dict[str, str]] = []
    day = _query_date("date", date, problems)
    start = _query_time("start_time", start_time, problems)
    end = _query_time("end_time", end_time, problems)
    features = None
    try:
        features = _features(feature)
    except ValidationFailed as exc:
        problems += exc.details["fields"]
    if start is not None and end is not None and start >= end:
        problems.append({"field": "end_time", "problem": "start_time must be before end_time"})
    if problems:
        raise ValidationFailed(problems)
    assert day is not None and start is not None and end is not None
    found = rooms.free_rooms(
        db,
        local_now(settings.clock),
        settings.holidays,
        day,
        start,
        end,
        branch_id=branch_id,
        kind=kind,
        min_capacity=min_capacity,
        features=features,
    )
    return paginate_sequence([room_out(r) for r in found], page)


@router.get("/rooms/{room_id}", response_model=RoomOut)
def get_room(room_id: RoomId, db: SessionDep, _: AnyUser) -> RoomOut:
    return room_out(rooms.get_room_or_404(db, room_id))


@router.patch("/rooms/{room_id}", response_model=RoomOut)
def update_room(room_id: RoomId, body: RoomPatchIn, request: Request, db: SessionDep, admin: AdminOnly) -> RoomOut:
    now = local_now(request.app.state.settings.clock)
    room = rooms.get_room_or_404(db, room_id)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    return room_out(rooms.update_room(db, now, admin.user, room, fields))


@router.get("/rooms/{room_id}/availability", response_model=AvailabilityOut)
def room_availability(
    room_id: RoomId,
    request: Request,
    db: SessionDep,
    principal: AnyUser,
    date: Annotated[str | None, Query()] = None,
) -> AvailabilityOut:
    settings = request.app.state.settings
    problems: list[dict[str, str]] = []
    day = _query_date("date", date, problems)
    if problems:
        raise ValidationFailed(problems)
    assert day is not None
    room = rooms.get_room_or_404(db, room_id)
    return rooms.availability(
        db,
        local_now(settings.clock),
        room,
        day,
        settings.holidays,
        staff=_is_staff(principal),
        member_id=principal.user.member_id,
    )


# --- bookings --------------------------------------------------------------------------------


@router.post("/room-bookings", response_model=RoomBookingOut, status_code=201)
def create_booking(body: RoomBookingCreateIn, request: Request, db: SessionDep, principal: CurrentPrincipal) -> RoomBookingOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    if principal.user.role == "member":
        if body.member_id is not None:
            raise ValidationFailed.single("member_id", "members book for themselves and must not send member_id")
        organizer_id = _own_member_id(principal)
    else:
        if body.member_id is None:
            raise ValidationFailed.single("member_id", "member_id is required for librarians and admins")
        organizer_id = body.member_id
    if organizer_id in body.participant_ids:
        raise ValidationFailed.single("participant_ids", "the organizer cannot be a participant")
    booking = bookings.create_booking(
        db,
        now,
        settings.holidays,
        principal.user,
        room_id=body.room_id,
        organizer_id=organizer_id,
        day=body.date,
        start=body.start_time,
        end=body.end_time,
        participant_ids=body.participant_ids,
        purpose=body.purpose,
    )
    return _booking_out(db, booking)


@router.get("/room-bookings", response_model=Page[RoomBookingOut])
def list_bookings(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[BookingStatus | None, Query()] = None,
    room_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    member_id: Annotated[int | None, Query()] = None,
) -> Page[RoomBookingOut]:
    stmt = bookings.booking_list_stmt(
        person_id=member_id,
        status=status,
        room_id=room_id,
        branch_id=branch_id,
        first=_optional_date("from", first),
        last=_optional_date("to", to),
    )
    return paginate(db, stmt, page, lambda b: _booking_out(db, b))


@router.post("/room-bookings/process", response_model=ProcessOut)
def process_bookings(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    now = local_now(request.app.state.settings.clock)
    no_shows, completed, ban_count = bookings.process(db, now, staff.user)
    return ProcessOut(no_shows=no_shows, completed=completed, bans=ban_count)


@router.post("/room-bookings/run-reminders", response_model=RoomRemindersOut)
def run_room_reminders(request: Request, db: SessionDep, staff: StaffOnly) -> RoomRemindersOut:
    settings = request.app.state.settings
    count = bookings.run_reminders(db, local_now(settings.clock), staff.user, settings.holidays)
    return RoomRemindersOut(room_reminders=count)


@router.get("/room-bookings/{booking_id}", response_model=RoomBookingOut)
def get_booking(booking_id: BookingId, db: SessionDep, principal: CurrentPrincipal) -> RoomBookingOut:
    booking = bookings.get_booking_or_404(db, booking_id)
    if principal.user.role == "member" and not (
        principal.user.member_id is not None and is_person(booking, principal.user.member_id)
    ):
        raise Forbidden("Only the persons of a booking can read it")
    return _booking_out(db, booking)


@router.get("/members/{member_id}/room-bookings", response_model=Page[RoomBookingOut])
def list_member_bookings(
    member_id: MemberId,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    status: Annotated[BookingStatus | None, Query()] = None,
    room_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> Page[RoomBookingOut]:
    first_date = _optional_date("from", first)
    last_date = _optional_date("to", to)
    member: Member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = bookings.booking_list_stmt(
        person_id=member.id, status=status, room_id=room_id, branch_id=branch_id, first=first_date, last=last_date
    )
    return paginate(db, stmt, page, lambda b: _booking_out(db, b))


@router.patch("/room-bookings/{booking_id}", response_model=RoomBookingOut)
def update_booking(
    booking_id: BookingId, body: RoomBookingPatchIn, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> RoomBookingOut:
    now = local_now(request.app.state.settings.clock)
    booking = bookings.get_booking_or_404(db, booking_id)
    _require_organizer(principal, booking)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    return _booking_out(db, bookings.update_booking(db, now, principal.user, booking, fields))


@router.post("/room-bookings/{booking_id}/cancel", response_model=RoomBookingOut)
def cancel_booking(booking_id: BookingId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> RoomBookingOut:
    now = local_now(request.app.state.settings.clock)
    booking = bookings.get_booking_or_404(db, booking_id)
    by_organizer = _require_organizer(principal, booking)
    return _booking_out(db, bookings.cancel(db, now, principal.user, booking, by_organizer=by_organizer))


@router.post("/room-bookings/{booking_id}/leave", response_model=RoomBookingOut)
def leave_booking(booking_id: BookingId, request: Request, db: SessionDep, principal: MemberOnly) -> RoomBookingOut:
    now = local_now(request.app.state.settings.clock)
    booking = bookings.get_booking_or_404(db, booking_id)
    member_id = principal.user.member_id
    if member_id is None or member_id not in booking.participant_ids:
        raise Forbidden("Only a participant can leave a booking")
    return _booking_out(db, bookings.leave_booking(db, now, principal.user, booking, member_id))


@router.post("/room-bookings/{booking_id}/check-in", response_model=RoomBookingOut)
def check_in(booking_id: BookingId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> RoomBookingOut:
    now = local_now(request.app.state.settings.clock)
    booking = bookings.get_booking_or_404(db, booking_id)
    _require_organizer(principal, booking)
    return _booking_out(db, bookings.check_in(db, now, principal.user, booking))


@router.post("/room-bookings/{booking_id}/check-out", response_model=RoomBookingOut)
def check_out(booking_id: BookingId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> RoomBookingOut:
    now = local_now(request.app.state.settings.clock)
    booking = bookings.get_booking_or_404(db, booking_id)
    _require_organizer(principal, booking)
    return _booking_out(db, bookings.check_out(db, now, principal.user, booking))


# --- bans ------------------------------------------------------------------------------------


@router.get("/members/{member_id}/room-bans", response_model=Page[RoomBanOut])
def list_member_bans(
    member_id: MemberId, request: Request, db: SessionDep, principal: CurrentPrincipal, page: PageDep
) -> Page[RoomBanOut]:
    today = local_now(request.app.state.settings.clock).date()
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = (
        sa.select(RoomBan).where(RoomBan.member_id == member.id).order_by(RoomBan.starts_on.desc(), RoomBan.id.desc())
    )
    return paginate(db, stmt, page, lambda ban: ban_out(ban, today))


@router.post("/members/{member_id}/room-bans", response_model=RoomBanOut, status_code=201)
def create_ban(member_id: MemberId, body: RoomBanCreateIn, request: Request, db: SessionDep, admin: AdminOnly) -> RoomBanOut:
    now = local_now(request.app.state.settings.clock)
    problems: list[dict[str, str]] = []
    if body.starts_on < now.date():
        problems.append({"field": "starts_on", "problem": "starts_on must not be before today"})
    if body.ends_on < body.starts_on:
        problems.append({"field": "ends_on", "problem": "ends_on must not be before starts_on"})
    if problems:
        raise ValidationFailed(problems)
    member = get_member_or_404(db, member_id)
    ban = bans.create_ban(
        db, now, admin.user.id, member.id, body.starts_on, body.ends_on, "staff", body.note, created_by=admin.user.id
    )
    return ban_out(ban, now.date())


@router.post("/room-bans/{ban_id}/lift", response_model=RoomBanOut)
def lift_ban(ban_id: BanId, request: Request, db: SessionDep, admin: AdminOnly) -> RoomBanOut:
    now = local_now(request.app.state.settings.clock)
    ban = bans.get_ban_or_404(db, ban_id)
    return ban_out(bans.lift_ban(db, now, admin.user, ban), now.date())
