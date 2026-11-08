"""Interlibrary loan endpoints (section 26.4)."""

from __future__ import annotations

from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel

from lms.auth.deps import AdminOnly, CurrentPrincipal, Principal, StaffOnly
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, ValidationFailed, reference_not_found
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.core.text import normalize
from lms.ill import outgoing as outgoing_service
from lms.ill import partners
from lms.ill import requests as request_service
from lms.ill.models import IllPartner, IllRequest
from lms.ill.schemas import (
    BranchIn,
    OutgoingCreateIn,
    OutgoingOut,
    OutgoingStatus,
    PartnerCreateIn,
    PartnerOut,
    PartnerPatchIn,
    ProcessOut,
    ReceiveIn,
    RejectIn,
    RenewalAnswerIn,
    RequestCreateIn,
    RequestOut,
    RequestStatus,
    SendIn,
    ShipIn,
    request_out,
)
from lms.members.models import Member
from lms.members.service import get_member_or_404

router = APIRouter(tags=["interlibrary loans"])

PartnerId = Annotated[int, Path(ge=1)]
RequestId = Annotated[int, Path(ge=1)]
OutgoingId = Annotated[int, Path(ge=1)]
MemberId = Annotated[int, Path(ge=1)]


def _fields_of(body: BaseModel) -> dict[str, Any]:
    """The parsed values of a request body (``model_dump`` would serialize amounts to strings)."""
    return {name: getattr(body, name) for name in type(body).model_fields}


def _own_or_staff(principal: Principal, member_id: int) -> None:
    """LIB-AUTH-25."""
    if principal.user.role == "member" and principal.user.member_id != member_id:
        raise Forbidden("Only your own interlibrary requests can be accessed")


def _out(request: IllRequest, now) -> RequestOut:  # noqa: ANN001
    return request_out(request, now.date())


# --- partners ---------------------------------------------------------------------


@router.post("/ill-partners", response_model=PartnerOut, status_code=201)
def create_partner(body: PartnerCreateIn, request: Request, db: SessionDep, admin: AdminOnly) -> PartnerOut:
    now = local_now(request.app.state.settings.clock)
    return partners.to_out(db, partners.create_partner(db, now, admin.user, **_fields_of(body)))


@router.get("/ill-partners", response_model=Page[PartnerOut])
def list_partners(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    is_active: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> Page[PartnerOut]:
    stmt = sa.select(IllPartner).order_by(IllPartner.code, IllPartner.id)
    if is_active is not None:
        stmt = stmt.where(IllPartner.is_active == is_active)
    needle = normalize(q.strip()) if q is not None else ""
    if not needle:
        return paginate(db, stmt, page, lambda p: partners.to_out(db, p))
    # Case-insensitive matching follows LIB-COM-30, which SQLite cannot do for Turkish letters.
    found = [p for p in db.scalars(stmt) if partners.matches(p, needle)]
    result = paginate_sequence(found, page)
    return Page[PartnerOut](
        items=[partners.to_out(db, p) for p in result.items], page=page.page, page_size=page.page_size, total=result.total
    )


@router.get("/ill-partners/{partner_id}", response_model=PartnerOut)
def get_partner(partner_id: PartnerId, db: SessionDep, _: StaffOnly) -> PartnerOut:
    return partners.to_out(db, partners.get_partner_or_404(db, partner_id))


@router.patch("/ill-partners/{partner_id}", response_model=PartnerOut)
def update_partner(
    partner_id: PartnerId, body: PartnerPatchIn, request: Request, db: SessionDep, admin: AdminOnly
) -> PartnerOut:
    now = local_now(request.app.state.settings.clock)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    partner = partners.get_partner_or_404(db, partner_id)
    return partners.to_out(db, partners.update_partner(db, now, admin.user, partner, fields))


# --- incoming requests --------------------------------------------------------------


@router.post("/ill-requests", response_model=RequestOut, status_code=201)
def create_request(body: RequestCreateIn, request: Request, db: SessionDep, principal: CurrentPrincipal) -> RequestOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    if principal.user.role == "member":
        if body.member_id is not None:
            raise ValidationFailed.single("member_id", "member_id must not be sent by a member")
        member_id = principal.user.member_id
        if member_id is None:
            raise Forbidden("The authenticated user has no member record")
    else:
        if body.member_id is None:
            raise ValidationFailed.single("member_id", "member_id is required")
        member_id = body.member_id
    member = db.get(Member, member_id)
    if member is None:
        raise reference_not_found("member_id", member_id)
    created = request_service.create_request(
        db, now, principal.user, settings.holidays, member, title=body.title, author=body.author, isbn=body.isbn
    )
    return _out(created, now)


@router.get("/ill-requests", response_model=Page[RequestOut])
def list_requests(
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[RequestStatus | None, Query()] = None,
    partner_id: Annotated[int | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
    member_id: Annotated[int | None, Query()] = None,
) -> Page[RequestOut]:
    now = local_now(request.app.state.settings.clock)
    stmt = request_service.request_list_stmt(
        now.date(), member_id=member_id, status=status, partner_id=partner_id, overdue=overdue
    )
    return paginate(db, stmt, page, lambda r: _out(r, now))


@router.get("/ill-requests/{request_id}", response_model=RequestOut)
def get_request(request_id: RequestId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> RequestOut:
    now = local_now(request.app.state.settings.clock)
    found = request_service.get_request_or_404(db, request_id)
    _own_or_staff(principal, found.member_id)
    return _out(found, now)


@router.get("/members/{member_id}/ill-requests", response_model=Page[RequestOut])
def list_member_requests(
    member_id: MemberId,
    request: Request,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    status: Annotated[RequestStatus | None, Query()] = None,
    partner_id: Annotated[int | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
) -> Page[RequestOut]:
    now = local_now(request.app.state.settings.clock)
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = request_service.request_list_stmt(
        now.date(), member_id=member.id, status=status, partner_id=partner_id, overdue=overdue
    )
    return paginate(db, stmt, page, lambda r: _out(r, now))


@router.post("/ill-requests/{request_id}/send", response_model=RequestOut)
def send_request(request_id: RequestId, body: SendIn, request: Request, db: SessionDep, staff: StaffOnly) -> RequestOut:
    now = local_now(request.app.state.settings.clock)
    found = request_service.get_request_or_404(db, request_id)
    return _out(request_service.send(db, now, staff.user, found, body.partner_id), now)


@router.post("/ill-requests/{request_id}/reject", response_model=RequestOut)
def reject_request(
    request_id: RequestId, body: RejectIn, request: Request, db: SessionDep, staff: StaffOnly
) -> RequestOut:
    now = local_now(request.app.state.settings.clock)
    found = request_service.get_request_or_404(db, request_id)
    return _out(request_service.reject(db, now, staff.user, found, body.reason), now)


@router.post("/ill-requests/{request_id}/receive", response_model=RequestOut)
def receive_request(
    request_id: RequestId, body: ReceiveIn, request: Request, db: SessionDep, staff: StaffOnly
) -> RequestOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    found = request_service.get_request_or_404(db, request_id)
    received = request_service.receive(
        db, now, staff.user, settings.holidays, found,
        partner_due_on=body.partner_due_on,
        replacement_cost=body.replacement_cost,
        pickup_branch_id=body.pickup_branch_id,
    )
    return _out(received, now)


@router.post("/ill-requests/{request_id}/collect", response_model=RequestOut)
def collect_request(request_id: RequestId, request: Request, db: SessionDep, staff: StaffOnly) -> RequestOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    found = request_service.get_request_or_404(db, request_id)
    return _out(request_service.collect(db, now, staff.user, settings.holidays, found), now)


@router.post("/ill-requests/{request_id}/return", response_model=RequestOut)
def return_request(
    request_id: RequestId, body: BranchIn, request: Request, db: SessionDep, staff: StaffOnly
) -> RequestOut:
    now = local_now(request.app.state.settings.clock)
    found = request_service.get_request_or_404(db, request_id)
    return _out(request_service.return_request(db, now, staff.user, found, body.branch_id), now)


@router.post("/ill-requests/{request_id}/close", response_model=RequestOut)
def close_request(request_id: RequestId, request: Request, db: SessionDep, staff: StaffOnly) -> RequestOut:
    now = local_now(request.app.state.settings.clock)
    found = request_service.get_request_or_404(db, request_id)
    return _out(request_service.close(db, now, staff.user, found), now)


@router.post("/ill-requests/{request_id}/report-lost", response_model=RequestOut)
def report_request_lost(request_id: RequestId, request: Request, db: SessionDep, staff: StaffOnly) -> RequestOut:
    now = local_now(request.app.state.settings.clock)
    found = request_service.get_request_or_404(db, request_id)
    return _out(request_service.report_lost(db, now, staff.user, found), now)


@router.post("/ill-requests/{request_id}/renewal-answer", response_model=RequestOut)
def renewal_answer(
    request_id: RequestId, body: RenewalAnswerIn, request: Request, db: SessionDep, staff: StaffOnly
) -> RequestOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    found = request_service.get_request_or_404(db, request_id)
    answered = request_service.renewal_answer(
        db, now, staff.user, settings.holidays, found, approved=body.approved, partner_due_on=body.partner_due_on
    )
    return _out(answered, now)


@router.post("/ill-requests/{request_id}/cancel", response_model=RequestOut)
def cancel_request(
    request_id: RequestId, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> RequestOut:
    now = local_now(request.app.state.settings.clock)
    found = request_service.get_request_or_404(db, request_id)
    _own_or_staff(principal, found.member_id)
    reason = "member_request" if principal.user.role == "member" else "staff_request"
    return _out(request_service.cancel(db, now, principal.user, found, reason=reason), now)


@router.post("/ill-requests/{request_id}/renewal-request", response_model=RequestOut)
def renewal_request(
    request_id: RequestId, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> RequestOut:
    now = local_now(request.app.state.settings.clock)
    found = request_service.get_request_or_404(db, request_id)
    _own_or_staff(principal, found.member_id)
    return _out(request_service.renewal_request(db, now, principal.user, found), now)


@router.post("/ill/process", response_model=ProcessOut)
def process(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    now = local_now(request.app.state.settings.clock)
    uncollected, overdue_outgoing = request_service.process(db, now, staff.user)
    return ProcessOut(uncollected=uncollected, overdue_outgoing=overdue_outgoing)


# --- outgoing requests --------------------------------------------------------------


@router.post("/ill-outgoing", response_model=OutgoingOut, status_code=201)
def create_outgoing(body: OutgoingCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> OutgoingOut:
    now = local_now(request.app.state.settings.clock)
    created = outgoing_service.create_outgoing(db, now, staff.user, partner_id=body.partner_id, book_id=body.book_id)
    return outgoing_service.to_out(db, created, now.date())


@router.get("/ill-outgoing", response_model=Page[OutgoingOut])
def list_outgoing(
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[OutgoingStatus | None, Query()] = None,
    partner_id: Annotated[int | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
) -> Page[OutgoingOut]:
    today = local_now(request.app.state.settings.clock).date()
    stmt = outgoing_service.outgoing_list_stmt(today, status=status, partner_id=partner_id, overdue=overdue)
    return paginate(db, stmt, page, lambda o: outgoing_service.to_out(db, o, today))


@router.get("/ill-outgoing/{outgoing_id}", response_model=OutgoingOut)
def get_outgoing(outgoing_id: OutgoingId, request: Request, db: SessionDep, _: StaffOnly) -> OutgoingOut:
    today = local_now(request.app.state.settings.clock).date()
    return outgoing_service.to_out(db, outgoing_service.get_outgoing_or_404(db, outgoing_id), today)


@router.post("/ill-outgoing/{outgoing_id}/ship", response_model=OutgoingOut)
def ship_outgoing(
    outgoing_id: OutgoingId, body: ShipIn, request: Request, db: SessionDep, staff: StaffOnly
) -> OutgoingOut:
    now = local_now(request.app.state.settings.clock)
    found = outgoing_service.get_outgoing_or_404(db, outgoing_id)
    return outgoing_service.to_out(db, outgoing_service.ship(db, now, staff.user, found, body.copy_id), now.date())


@router.post("/ill-outgoing/{outgoing_id}/decline", response_model=OutgoingOut)
def decline_outgoing(outgoing_id: OutgoingId, request: Request, db: SessionDep, staff: StaffOnly) -> OutgoingOut:
    now = local_now(request.app.state.settings.clock)
    found = outgoing_service.get_outgoing_or_404(db, outgoing_id)
    return outgoing_service.to_out(db, outgoing_service.decline(db, now, staff.user, found), now.date())


@router.post("/ill-outgoing/{outgoing_id}/returned", response_model=OutgoingOut)
def outgoing_returned(
    outgoing_id: OutgoingId, body: BranchIn, request: Request, db: SessionDep, staff: StaffOnly
) -> OutgoingOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    found = outgoing_service.get_outgoing_or_404(db, outgoing_id)
    done = outgoing_service.returned(db, now, staff.user, settings.holidays, found, body.branch_id)
    return outgoing_service.to_out(db, done, now.date())


@router.post("/ill-outgoing/{outgoing_id}/report-lost", response_model=OutgoingOut)
def outgoing_report_lost(
    outgoing_id: OutgoingId, request: Request, db: SessionDep, staff: StaffOnly
) -> OutgoingOut:
    now = local_now(request.app.state.settings.clock)
    found = outgoing_service.get_outgoing_or_404(db, outgoing_id)
    return outgoing_service.to_out(db, outgoing_service.report_lost(db, now, staff.user, found), now.date())
