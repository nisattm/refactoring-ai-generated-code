"""Digital resource endpoints (section 25.3)."""

from __future__ import annotations

import datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, Request

from lms.auth.deps import AdminOnly, AnyUser, CurrentPrincipal, Principal, StaffOnly
from lms.catalog.service import get_book_or_404
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, ValidationFailed, reference_not_found
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.core.timeutil import parse_date
from lms.digital import holds as hold_service
from lms.digital import lending, process as process_service, resources, sessions as session_service, state
from lms.digital.models import DigitalResource
from lms.digital.schemas import (
    ActionCreateIn,
    CalendarDayOut,
    CalendarOut,
    ExpiringLicenseOut,
    HoldOut,
    HoldStatus,
    LicenseCreateIn,
    LicenseOut,
    LicensePatchIn,
    LicenseRenewIn,
    LicenseStatus,
    LoanOut,
    LoanStatus,
    ProcessOut,
    ResourceCreateIn,
    ResourceKind,
    ResourceOut,
    ResourcePatchIn,
    SessionOut,
    expiring_license_out,
    hold_out,
    license_out,
    loan_out,
    session_out,
)
from lms.members.models import Member
from lms.members.service import get_member_or_404

router = APIRouter(tags=["digital"])

ResourceId = Annotated[int, Path(ge=1)]
LicenseId = Annotated[int, Path(ge=1)]
LoanId = Annotated[int, Path(ge=1)]
HoldId = Annotated[int, Path(ge=1)]
SessionId = Annotated[int, Path(ge=1)]
MemberId = Annotated[int, Path(ge=1)]
BookId = Annotated[int, Path(ge=1)]

MAX_CALENDAR_DAYS = 92


def _required_date(name: str, raw: str | None, problems: list[dict[str, str]]) -> datetime.date | None:
    if raw is None:
        problems.append({"field": name, "problem": "field required"})
        return None
    try:
        return parse_date(raw.strip())
    except ValueError:
        problems.append({"field": name, "problem": "expected a valid date in the form YYYY-MM-DD"})
        return None


def _own_or_staff(principal: Principal, member_id: int) -> None:
    """LIB-AUTH-25."""
    if principal.user.role == "member" and principal.user.member_id != member_id:
        raise Forbidden("Only your own digital data can be accessed")


def _acting_member_id(principal: Principal, body: ActionCreateIn) -> int:
    """``member_id`` in the body: staff must send it, a member must not (25.3)."""
    if principal.user.role == "member":
        if body.member_id is not None:
            raise ValidationFailed.single("member_id", "members act for themselves and must not send member_id")
        if principal.user.member_id is None:
            raise Forbidden("The authenticated user has no member record")
        member_id = principal.user.member_id
    else:
        if body.member_id is None:
            raise ValidationFailed.single("member_id", "member_id is required for librarians and admins")
        member_id = body.member_id
    return member_id


def _resolve(db: SessionDep, principal: Principal, body: ActionCreateIn) -> tuple[DigitalResource, Member]:
    member_id = _acting_member_id(principal, body)
    resource = db.get(DigitalResource, body.resource_id)
    if resource is None:
        raise reference_not_found("resource_id", body.resource_id)
    member = db.get(Member, member_id)
    if member is None:
        raise reference_not_found("member_id", member_id)
    return resource, member


# --- resources -------------------------------------------------------------------------------


@router.post("/digital-resources", response_model=ResourceOut, status_code=201)
def create_resource(body: ResourceCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> ResourceOut:
    now = local_now(request.app.state.settings.clock)
    return resources.counts_out(db, resources.create_resource(db, now, staff.user, body), now)


@router.get("/digital-resources", response_model=Page[ResourceOut])
def list_resources(
    request: Request,
    db: SessionDep,
    _: AnyUser,
    page: PageDep,
    kind: Annotated[ResourceKind | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    book_id: Annotated[int | None, Query()] = None,
) -> Page[ResourceOut]:
    now = local_now(request.app.state.settings.clock)
    stmt = resources.resource_list_stmt(kind=kind, is_active=is_active, q=q, book_id=book_id)
    return paginate(db, stmt, page, lambda r: resources.counts_out(db, r, now))


@router.get("/digital-resources/{resource_id}", response_model=ResourceOut)
def get_resource(resource_id: ResourceId, request: Request, db: SessionDep, _: AnyUser) -> ResourceOut:
    now = local_now(request.app.state.settings.clock)
    return resources.counts_out(db, state.get_resource_or_404(db, resource_id), now)


@router.patch("/digital-resources/{resource_id}", response_model=ResourceOut)
def update_resource(
    resource_id: ResourceId, body: ResourcePatchIn, request: Request, db: SessionDep, staff: StaffOnly
) -> ResourceOut:
    now = local_now(request.app.state.settings.clock)
    resource = state.get_resource_or_404(db, resource_id)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    return resources.counts_out(db, resources.update_resource(db, now, staff.user, resource, fields), now)


@router.get("/books/{book_id}/digital-resources", response_model=list[ResourceOut])
def book_resources(book_id: BookId, request: Request, db: SessionDep, _: AnyUser) -> list[ResourceOut]:
    now = local_now(request.app.state.settings.clock)
    book = get_book_or_404(db, book_id)
    stmt = (
        sa.select(DigitalResource)
        .where(DigitalResource.book_id == book.id, DigitalResource.kind == "ebook", DigitalResource.is_active.is_(True))
        .order_by(DigitalResource.id)
    )
    return [resources.counts_out(db, r, now) for r in db.scalars(stmt)]


@router.get("/digital-resources/{resource_id}/calendar", response_model=CalendarOut)
def resource_calendar(
    resource_id: ResourceId,
    db: SessionDep,
    _: AnyUser,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> CalendarOut:
    problems: list[dict[str, str]] = []
    start = _required_date("from", first, problems)
    end = _required_date("to", to, problems)
    if problems:
        raise ValidationFailed(problems)
    assert start is not None and end is not None
    if start > end:
        raise ValidationFailed.single("from", "from must not be after to")
    if (end - start).days >= MAX_CALENDAR_DAYS:
        raise ValidationFailed.single("to", f"the range must not be longer than {MAX_CALENDAR_DAYS} days")
    resource = state.get_resource_or_404(db, resource_id)
    days = [CalendarDayOut(date=day.isoformat(), capacity=cap) for day, cap in resources.calendar(db, resource, start, end)]
    return CalendarOut(resource_id=resource.id, days=days)


# --- licenses --------------------------------------------------------------------------------


@router.post("/digital-resources/{resource_id}/licenses", response_model=LicenseOut, status_code=201)
def add_license(
    resource_id: ResourceId, body: LicenseCreateIn, request: Request, db: SessionDep, admin: AdminOnly
) -> LicenseOut:
    now = local_now(request.app.state.settings.clock)
    resource = state.get_resource_or_404(db, resource_id)
    return license_out(resources.add_license(db, now, admin.user, resource, body), now.date())


@router.get("/digital-resources/{resource_id}/licenses", response_model=Page[LicenseOut])
def list_licenses(
    resource_id: ResourceId,
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[LicenseStatus | None, Query()] = None,
) -> Page[LicenseOut]:
    today = local_now(request.app.state.settings.clock).date()
    resource = state.get_resource_or_404(db, resource_id)
    items = [license_out(lic, today) for lic in resources.license_list(db, resource.id, today, status)]
    return paginate_sequence(items, page)


@router.get("/digital-licenses", response_model=Page[ExpiringLicenseOut])
def expiring_licenses(
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    ending_within_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> Page[ExpiringLicenseOut]:
    today = local_now(request.app.state.settings.clock).date()
    items = [expiring_license_out(lic, today, title) for lic, title in resources.expiring_licenses(db, today, ending_within_days)]
    return paginate_sequence(items, page)


@router.patch("/digital-licenses/{license_id}", response_model=LicenseOut)
def update_license(
    license_id: LicenseId, body: LicensePatchIn, request: Request, db: SessionDep, admin: AdminOnly
) -> LicenseOut:
    now = local_now(request.app.state.settings.clock)
    lic = resources.get_license_or_404(db, license_id)
    return license_out(resources.update_license(db, now, admin.user, lic, body), now.date())


@router.post("/digital-licenses/{license_id}/cancel", response_model=LicenseOut)
def cancel_license(license_id: LicenseId, request: Request, db: SessionDep, admin: AdminOnly) -> LicenseOut:
    now = local_now(request.app.state.settings.clock)
    lic = resources.get_license_or_404(db, license_id)
    return license_out(resources.cancel_license(db, now, admin.user, lic), now.date())


@router.post("/digital-licenses/{license_id}/renew", response_model=LicenseOut, status_code=201)
def renew_license(
    license_id: LicenseId, body: LicenseRenewIn, request: Request, db: SessionDep, admin: AdminOnly
) -> LicenseOut:
    now = local_now(request.app.state.settings.clock)
    lic = resources.get_license_or_404(db, license_id)
    return license_out(resources.renew_license(db, now, admin.user, lic, body), now.date())


# --- loans -----------------------------------------------------------------------------------


@router.post("/digital-loans", response_model=LoanOut, status_code=201)
def create_loan(body: ActionCreateIn, request: Request, db: SessionDep, principal: CurrentPrincipal) -> LoanOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    resource, member = _resolve(db, principal, body)
    return loan_out(lending.borrow(db, now, principal.user, settings.holidays, resource, member), now)


@router.get("/digital-loans", response_model=Page[LoanOut])
def list_loans(
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[LoanStatus | None, Query()] = None,
    resource_id: Annotated[int | None, Query()] = None,
    member_id: Annotated[int | None, Query()] = None,
) -> Page[LoanOut]:
    now = local_now(request.app.state.settings.clock)
    stmt = lending.loan_list_stmt(now, member_id=member_id, resource_id=resource_id, status=status)
    return paginate(db, stmt, page, lambda loan: loan_out(loan, now))


@router.get("/digital-loans/{loan_id}", response_model=LoanOut)
def get_loan(loan_id: LoanId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> LoanOut:
    now = local_now(request.app.state.settings.clock)
    loan = lending.get_loan_or_404(db, loan_id)
    _own_or_staff(principal, loan.member_id)
    return loan_out(loan, now)


@router.get("/members/{member_id}/digital-loans", response_model=Page[LoanOut])
def list_member_loans(
    member_id: MemberId,
    request: Request,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    status: Annotated[LoanStatus | None, Query()] = None,
    resource_id: Annotated[int | None, Query()] = None,
) -> Page[LoanOut]:
    now = local_now(request.app.state.settings.clock)
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = lending.loan_list_stmt(now, member_id=member.id, resource_id=resource_id, status=status)
    return paginate(db, stmt, page, lambda loan: loan_out(loan, now))


@router.post("/digital-loans/{loan_id}/return", response_model=LoanOut)
def return_loan(loan_id: LoanId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> LoanOut:
    now = local_now(request.app.state.settings.clock)
    loan = lending.get_loan_or_404(db, loan_id)
    _own_or_staff(principal, loan.member_id)
    return loan_out(lending.return_loan(db, now, principal.user, loan), now)


@router.post("/digital-loans/{loan_id}/renew", response_model=LoanOut)
def renew_loan(loan_id: LoanId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> LoanOut:
    now = local_now(request.app.state.settings.clock)
    loan = lending.get_loan_or_404(db, loan_id)
    _own_or_staff(principal, loan.member_id)
    return loan_out(lending.renew(db, now, principal.user, loan), now)


# --- holds -----------------------------------------------------------------------------------


@router.post("/digital-holds", response_model=HoldOut, status_code=201)
def create_hold(body: ActionCreateIn, request: Request, db: SessionDep, principal: CurrentPrincipal) -> HoldOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    resource, member = _resolve(db, principal, body)
    hold = hold_service.place_hold(db, now, principal.user, settings.holidays, resource, member)
    return hold_out(hold, state.hold_position(db, hold))


@router.get("/digital-resources/{resource_id}/holds", response_model=Page[HoldOut])
def list_resource_holds(
    resource_id: ResourceId,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[HoldStatus, Query()] = "waiting",
) -> Page[HoldOut]:
    resource = state.get_resource_or_404(db, resource_id)
    stmt = hold_service.resource_hold_stmt(resource.id, status)
    return paginate(db, stmt, page, lambda h: hold_out(h, state.hold_position(db, h)))


@router.get("/members/{member_id}/digital-holds", response_model=Page[HoldOut])
def list_member_holds(
    member_id: MemberId,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    status: Annotated[HoldStatus | None, Query()] = None,
) -> Page[HoldOut]:
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = hold_service.member_hold_stmt(member.id, status)
    return paginate(db, stmt, page, lambda h: hold_out(h, state.hold_position(db, h)))


@router.post("/digital-holds/{hold_id}/cancel", response_model=HoldOut)
def cancel_hold(hold_id: HoldId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> HoldOut:
    now = local_now(request.app.state.settings.clock)
    hold = hold_service.get_hold_or_404(db, hold_id)
    _own_or_staff(principal, hold.member_id)
    hold_service.cancel(db, now, principal.user, hold, by_member=principal.user.role == "member")
    return hold_out(hold, state.hold_position(db, hold))


# --- sessions --------------------------------------------------------------------------------


@router.post("/digital-sessions", response_model=SessionOut, status_code=201)
def open_session(body: ActionCreateIn, request: Request, db: SessionDep, principal: CurrentPrincipal) -> SessionOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    resource, member = _resolve(db, principal, body)
    return session_out(session_service.open_session(db, now, principal.user, settings.holidays, resource, member), now)


@router.post("/digital-sessions/{session_id}/close", response_model=SessionOut)
def close_session(session_id: SessionId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> SessionOut:
    now = local_now(request.app.state.settings.clock)
    session = session_service.get_session_or_404(db, session_id)
    _own_or_staff(principal, session.member_id)
    return session_out(session_service.close_session(db, now, session), now)


@router.get("/members/{member_id}/digital-sessions", response_model=Page[SessionOut])
def list_member_sessions(
    member_id: MemberId,
    request: Request,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    open: Annotated[bool | None, Query()] = None,
    resource_id: Annotated[int | None, Query()] = None,
) -> Page[SessionOut]:
    now = local_now(request.app.state.settings.clock)
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = session_service.member_session_stmt(member.id, now, open_=open, resource_id=resource_id)
    return paginate(db, stmt, page, lambda s: session_out(s, now))


# --- processing ------------------------------------------------------------------------------


@router.post("/digital/process", response_model=ProcessOut)
def process(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    now = local_now(request.app.state.settings.clock)
    expired_loans, expired_holds, holds_ready, due_soon = process_service.process(db, now, staff.user)
    return ProcessOut(
        expired_loans=expired_loans, expired_holds=expired_holds, holds_ready=holds_ready, due_soon_notices=due_soon
    )
