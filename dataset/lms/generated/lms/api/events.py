"""Event endpoints (section 28.3)."""

from __future__ import annotations

import datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, Request

from lms.auth.deps import AnyUser, CurrentPrincipal, Principal, StaffOnly
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, NotFound, ValidationFailed, reference_not_found
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.core.timeutil import parse_date
from lms.events import events as event_service
from lms.events import process as process_service
from lms.events import registrations as registration_service
from lms.events import usage
from lms.events.models import EventBan, EventRegistration
from lms.events.schemas import (
    AttendanceOut,
    BanOut,
    EventCreateIn,
    EventKind,
    EventOut,
    EventPatchIn,
    EventStatus,
    ProcessOut,
    RegistrationCreateIn,
    RegistrationOut,
    RegistrationStatus,
    SeriesCancelledOut,
    SeriesCreatedOut,
    SeriesCreateIn,
    SkippedOut,
    ban_out,
)
from lms.members.models import Member
from lms.members.service import get_member_or_404

router = APIRouter(tags=["events"])

EventId = Annotated[int, Path(ge=1)]
SeriesId = Annotated[int, Path(ge=1)]
RegistrationId = Annotated[int, Path(ge=1)]
MemberId = Annotated[int, Path(ge=1)]


def _optional_date(name: str, raw: str | None) -> datetime.date | None:
    if raw is None:
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        raise ValidationFailed.single(name, "expected a valid date in the form YYYY-MM-DD") from None


def _is_staff(principal: Principal) -> bool:
    return principal.user.role != "member"


def _own_or_staff(principal: Principal, member_id: int) -> None:
    """LIB-AUTH-25."""
    if principal.user.role == "member" and principal.user.member_id != member_id:
        raise Forbidden("Only your own event data can be accessed")


# --- events ------------------------------------------------------------------------------------


@router.post("/events", response_model=EventOut, status_code=201)
def create_event(body: EventCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> EventOut:
    settings = request.app.state.settings
    event = event_service.create_event(
        db, local_now(settings.clock), settings.holidays, staff.user, body.model_dump()
    )
    return event_service.to_out(db, event)


@router.get("/events", response_model=Page[EventOut])
def list_events(
    db: SessionDep,
    principal: AnyUser,
    page: PageDep,
    branch_id: Annotated[int | None, Query()] = None,
    kind: Annotated[EventKind | None, Query()] = None,
    status: Annotated[EventStatus | None, Query()] = None,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    series_id: Annotated[int | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> Page[EventOut]:
    selection = event_service.list_events(
        db,
        include_drafts=_is_staff(principal),
        branch_id=branch_id,
        kind=kind,
        status=status,
        first=_optional_date("from", first),
        last=_optional_date("to", to),
        series_id=series_id,
        q=q,
    )
    if isinstance(selection, list):
        chunk = paginate_sequence(selection, page)
        return Page[EventOut](
            items=[event_service.to_out(db, e) for e in chunk.items],
            page=chunk.page,
            page_size=chunk.page_size,
            total=chunk.total,
        )
    return paginate(db, selection, page, lambda e: event_service.to_out(db, e))


@router.post("/events/process", response_model=ProcessOut)
def process_events(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    completed, no_shows, bans, reminders = process_service.process(db, local_now(request.app.state.settings.clock), staff.user)
    return ProcessOut(completed_events=completed, no_shows=no_shows, bans=bans, reminders=reminders)


@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: EventId, db: SessionDep, principal: AnyUser) -> EventOut:
    event = event_service.get_event_or_404(db, event_id)
    if event.status == "draft" and not _is_staff(principal):
        raise NotFound(f"Event {event_id} does not exist", details={"resource": "event", "id": event_id})
    return event_service.to_out(db, event)


@router.patch("/events/{event_id}", response_model=EventOut)
def update_event(event_id: EventId, body: EventPatchIn, request: Request, db: SessionDep, staff: StaffOnly) -> EventOut:
    settings = request.app.state.settings
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    nulls = [name for name, value in fields.items() if value is None and name != "room_id"]
    if nulls:
        raise ValidationFailed([{"field": name, "problem": "value must not be null"} for name in nulls])
    event = event_service.get_event_or_404(db, event_id)
    updated = event_service.update_event(db, local_now(settings.clock), settings.holidays, staff.user, event, fields)
    return event_service.to_out(db, updated)


@router.post("/events/{event_id}/publish", response_model=EventOut)
def publish_event(event_id: EventId, request: Request, db: SessionDep, staff: StaffOnly) -> EventOut:
    settings = request.app.state.settings
    event = event_service.get_event_or_404(db, event_id)
    published = event_service.publish(db, local_now(settings.clock), settings.holidays, staff.user, event)
    return event_service.to_out(db, published)


@router.post("/events/{event_id}/cancel", response_model=EventOut)
def cancel_event(event_id: EventId, request: Request, db: SessionDep, staff: StaffOnly) -> EventOut:
    event = event_service.get_event_or_404(db, event_id)
    return event_service.to_out(db, event_service.cancel(db, local_now(request.app.state.settings.clock), staff.user, event))


# --- series --------------------------------------------------------------------------------------


@router.post("/event-series", response_model=SeriesCreatedOut, status_code=201)
def create_series(body: SeriesCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> SeriesCreatedOut:
    settings = request.app.state.settings
    data = body.model_dump(exclude={"first_date", "weeks"})
    series_id, created, skipped = event_service.create_series(
        db, local_now(settings.clock), settings.holidays, staff.user, data, body.first_date, body.weeks
    )
    return SeriesCreatedOut(
        series_id=series_id, created=created, skipped=[SkippedOut(**s) for s in skipped]
    )


@router.post("/event-series/{series_id}/cancel", response_model=SeriesCancelledOut)
def cancel_series(series_id: SeriesId, request: Request, db: SessionDep, staff: StaffOnly) -> SeriesCancelledOut:
    cancelled = event_service.cancel_series(db, local_now(request.app.state.settings.clock), staff.user, series_id)
    return SeriesCancelledOut(cancelled=cancelled)


# --- registrations ---------------------------------------------------------------------------------


@router.post("/events/{event_id}/registrations", response_model=RegistrationOut, status_code=201)
def register(
    event_id: EventId, body: RegistrationCreateIn, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> RegistrationOut:
    settings = request.app.state.settings
    if principal.user.role == "member":
        if body.member_id is not None:
            raise ValidationFailed.single("member_id", "members register themselves and must not send member_id")
        if principal.user.member_id is None:
            raise Forbidden("The authenticated user has no member record")
        member_id = principal.user.member_id
    else:
        if body.member_id is None:
            raise ValidationFailed.single("member_id", "member_id is required for librarians and admins")
        member_id = body.member_id
    event = event_service.get_event_or_404(db, event_id)
    member = db.get(Member, member_id)
    if member is None:
        raise reference_not_found("member_id", member_id)
    reg = registration_service.register(db, local_now(settings.clock), settings.holidays, principal.user, event, member)
    return registration_service.to_out(db, reg, event)


@router.get("/events/{event_id}/registrations", response_model=Page[RegistrationOut])
def list_event_registrations(
    event_id: EventId,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[RegistrationStatus | None, Query()] = None,
) -> Page[RegistrationOut]:
    event = event_service.get_event_or_404(db, event_id)
    stmt = registration_service.event_registrations_stmt(event.id, status)
    return paginate(db, stmt, page, lambda r: registration_service.to_out(db, r, event))


@router.get("/members/{member_id}/event-registrations", response_model=Page[RegistrationOut])
def list_member_registrations(
    member_id: MemberId,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    status: Annotated[RegistrationStatus | None, Query()] = None,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> Page[RegistrationOut]:
    first_date = _optional_date("from", first)
    last_date = _optional_date("to", to)
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = registration_service.member_registrations_stmt(member.id, status, first_date, last_date)
    return paginate(db, stmt, page, lambda r: registration_service.to_out(db, r))


def _registration_for(db: SessionDep, principal: Principal, registration_id: int) -> EventRegistration:
    reg = registration_service.get_registration_or_404(db, registration_id)
    _own_or_staff(principal, reg.member_id)
    return reg


@router.post("/event-registrations/{registration_id}/cancel", response_model=RegistrationOut)
def cancel_registration(
    registration_id: RegistrationId, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> RegistrationOut:
    now = local_now(request.app.state.settings.clock)
    reg = _registration_for(db, principal, registration_id)
    cancelled = registration_service.cancel(db, now, principal.user, reg, by_member=principal.user.role == "member")
    return registration_service.to_out(db, cancelled)


@router.post("/event-registrations/{registration_id}/check-in", response_model=RegistrationOut)
def check_in(registration_id: RegistrationId, request: Request, db: SessionDep, staff: StaffOnly) -> RegistrationOut:
    now = local_now(request.app.state.settings.clock)
    reg = registration_service.get_registration_or_404(db, registration_id)
    return registration_service.to_out(db, registration_service.check_in(db, now, staff.user, reg))


# --- bans -------------------------------------------------------------------------------------------


@router.get("/members/{member_id}/event-bans", response_model=Page[BanOut])
def list_member_bans(member_id: MemberId, db: SessionDep, principal: CurrentPrincipal, page: PageDep) -> Page[BanOut]:
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = sa.select(EventBan).where(EventBan.member_id == member.id).order_by(EventBan.starts_on, EventBan.id)
    return paginate(db, stmt, page, ban_out)


# --- report ----------------------------------------------------------------------------------------


@router.get("/reports/event-attendance", response_model=Page[AttendanceOut])
def event_attendance_report(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    kind: Annotated[EventKind | None, Query()] = None,
) -> Page[AttendanceOut]:
    problems: list[dict[str, str]] = []
    dates: dict[str, datetime.date] = {}
    for name, raw in (("from", first), ("to", to)):
        if raw is None:
            problems.append({"field": name, "problem": "field required"})
            continue
        try:
            dates[name] = parse_date(raw.strip())
        except ValueError:
            problems.append({"field": name, "problem": "expected a valid date in the form YYYY-MM-DD"})
    if problems:
        raise ValidationFailed(problems)
    start, end = dates["from"], dates["to"]
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days > 365:
        raise ValidationFailed.single("to", "the range must not be longer than 366 days including both ends")
    stmt = usage.attendance(db, start, end, branch_id=branch_id, kind=kind)
    return paginate(db, stmt, page, lambda e: usage.attendance_out(db, e))
