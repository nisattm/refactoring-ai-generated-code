"""Donor and donation endpoints (section 30.2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from lms.api.common import ensure_own_or_staff, is_member, optional_date, own_member, request_now
from lms.auth.deps import AdminOnly, AnyUser, CurrentPrincipal, Principal, StaffOnly
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, NotFound, ValidationFailed, reference_not_found
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.donations import donors as donor_service
from lms.donations import offers, receiving, review
from lms.donations.models import Donation, Donor
from lms.donations.rules import Level
from lms.donations.schemas import (
    DonationCreateIn,
    DonationOut,
    DonationPatchIn,
    DonationStatus,
    DonorCreateIn,
    DonorKind,
    DonorOut,
    DonorPatchIn,
    HistoryOut,
    MergeIn,
    ProcessOut,
    ReceiptOut,
    ReceiveIn,
    ReviewIn,
    SuggestionsOut,
    WallOut,
)
from lms.members.models import Member
from lms.members.service import get_member_or_404

router = APIRouter(tags=["donations"])

DonorId = Annotated[int, Path(ge=1)]
DonationId = Annotated[int, Path(ge=1)]
MemberId = Annotated[int, Path(ge=1)]


def _require_own(db: SessionDep, principal: Principal, donation: Donation, *, hide: bool) -> None:
    """LIB-AUTH-25; reading another member's donation is ``404`` (LIB-DON-13)."""
    if is_member(principal) and not offers.is_own(db, donation, principal.user.member_id):
        if hide:
            raise NotFound(
                f"Donation {donation.id} does not exist", details={"resource": "donation", "id": donation.id}
            )
        raise Forbidden("Only your own donations can be accessed")


def _donor_out(db: SessionDep, request: Request, donor: Donor) -> DonorOut:
    return donor_service.to_out(db, request_now(request), donor)


# --- donors ---------------------------------------------------------------------------------


@router.post("/donors", response_model=DonorOut, status_code=201)
def create_donor(body: DonorCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> DonorOut:
    now = request_now(request)
    donor = donor_service.create_donor(db, now, staff.user, body.model_dump())
    return donor_service.to_out(db, now, donor)


@router.get("/donors", response_model=Page[DonorOut])
def list_donors(
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    q: Annotated[str | None, Query()] = None,
    kind: Annotated[DonorKind | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    level: Annotated[Level | None, Query()] = None,
) -> Page[DonorOut]:
    now = request_now(request)
    donors = donor_service.list_donors(db, now, q=q, kind=kind, is_active=is_active, level=level)
    return paginate_sequence(donors, page)


@router.get("/donors/{donor_id}", response_model=DonorOut)
def get_donor(donor_id: DonorId, request: Request, db: SessionDep, _: StaffOnly) -> DonorOut:
    return _donor_out(db, request, donor_service.get_donor_or_404(db, donor_id))


@router.patch("/donors/{donor_id}", response_model=DonorOut)
def update_donor(donor_id: DonorId, body: DonorPatchIn, request: Request, db: SessionDep, staff: StaffOnly) -> DonorOut:
    now = request_now(request)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    nulls = [name for name in ("name", "anonymous", "is_active") if name in fields and fields[name] is None]
    if nulls:
        raise ValidationFailed([{"field": name, "problem": "value must not be null"} for name in nulls])
    donor = donor_service.get_donor_or_404(db, donor_id)
    return donor_service.to_out(db, now, donor_service.update_donor(db, now, staff.user, donor, fields))


@router.post("/donors/{donor_id}/merge", response_model=DonorOut)
def merge_donor(donor_id: DonorId, body: MergeIn, request: Request, db: SessionDep, admin: AdminOnly) -> DonorOut:
    now = request_now(request)
    if body.into_donor_id == donor_id:
        raise ValidationFailed.single("into_donor_id", "a donor cannot be merged into itself")
    donor = donor_service.get_donor_or_404(db, donor_id)
    target = db.get(Donor, body.into_donor_id)
    if target is None:
        raise reference_not_found("into_donor_id", body.into_donor_id)
    return donor_service.to_out(db, now, donor_service.merge(db, now, admin.user, donor, target))


@router.get("/donors/{donor_id}/history", response_model=HistoryOut)
def donor_history(donor_id: DonorId, db: SessionDep, _: StaffOnly) -> HistoryOut:
    return donor_service.history(db, donor_service.get_donor_or_404(db, donor_id))


@router.get("/donor-wall", response_model=WallOut)
def donor_wall(
    request: Request, db: SessionDep, _: AnyUser, year: Annotated[int | None, Query(ge=2000, le=2100)] = None
) -> WallOut:
    if year is None:
        year = request_now(request).year
    return donor_service.wall(db, year)


# --- donations: offers -----------------------------------------------------------------------


@router.post("/donations", response_model=DonationOut, status_code=201)
def offer_donation(body: DonationCreateIn, request: Request, db: SessionDep, principal: CurrentPrincipal) -> DonationOut:
    now = request_now(request)
    member: Member | None = None
    if is_member(principal):
        if body.donor_id is not None:
            raise ValidationFailed.single("donor_id", "members offer for themselves and must not send donor_id")
        member = own_member(db, principal)
    elif body.donor_id is None:
        raise ValidationFailed.single("donor_id", "donor_id is required for librarians and admins")
    donation = offers.offer(
        db,
        now,
        principal.user,
        member=member,
        donor_id=body.donor_id,
        branch_id=body.branch_id,
        note=body.note,
        items=body.items,
    )
    return offers.to_out(db, donation)


@router.get("/donations", response_model=Page[DonationOut])
def list_donations(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    status: Annotated[DonationStatus | None, Query()] = None,
    donor_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    first: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
) -> Page[DonationOut]:
    stmt = offers.list_stmt(
        status=status,
        donor_id=donor_id,
        branch_id=branch_id,
        first=optional_date("from", first),
        last=optional_date("to", to),
    )
    return paginate(db, stmt, page, lambda d: offers.to_out(db, d))


@router.post("/donations/process", response_model=ProcessOut)
def process_donations(request: Request, db: SessionDep, staff: StaffOnly) -> ProcessOut:
    now = request_now(request)
    return ProcessOut(expired=receiving.process(db, now, staff.user))


@router.get("/donations/{donation_id}", response_model=DonationOut)
def get_donation(donation_id: DonationId, db: SessionDep, principal: CurrentPrincipal) -> DonationOut:
    donation = offers.get_donation_or_404(db, donation_id)
    _require_own(db, principal, donation, hide=True)
    return offers.to_out(db, donation)


@router.get("/members/{member_id}/donations", response_model=Page[DonationOut])
def list_member_donations(
    member_id: MemberId, db: SessionDep, principal: CurrentPrincipal, page: PageDep
) -> Page[DonationOut]:
    member = get_member_or_404(db, member_id)
    ensure_own_or_staff(principal, member.id, "donations")
    return paginate(db, offers.list_stmt(member_id=member.id), page, lambda d: offers.to_out(db, d))


@router.patch("/donations/{donation_id}", response_model=DonationOut)
def update_donation(
    donation_id: DonationId, body: DonationPatchIn, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> DonationOut:
    now = request_now(request)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    nulls = [name for name, value in fields.items() if value is None]
    if nulls:
        raise ValidationFailed([{"field": name, "problem": "value must not be null"} for name in nulls])
    donation = offers.get_donation_or_404(db, donation_id)
    _require_own(db, principal, donation, hide=False)
    return offers.to_out(db, offers.update_offer(db, now, principal.user, donation, fields))


@router.post("/donations/{donation_id}/cancel", response_model=DonationOut)
def cancel_donation(
    donation_id: DonationId, request: Request, db: SessionDep, principal: CurrentPrincipal
) -> DonationOut:
    now = request_now(request)
    donation = offers.get_donation_or_404(db, donation_id)
    _require_own(db, principal, donation, hide=False)
    cancelled = offers.cancel(db, now, principal.user, donation, by_member=is_member(principal))
    return offers.to_out(db, cancelled)


# --- donations: review and receiving ------------------------------------------------------------


@router.get("/donations/{donation_id}/suggestions", response_model=SuggestionsOut)
def donation_suggestions(donation_id: DonationId, request: Request, db: SessionDep, _: StaffOnly) -> SuggestionsOut:
    now = request_now(request)
    return review.suggestions(db, now, offers.get_donation_or_404(db, donation_id))


@router.post("/donations/{donation_id}/review", response_model=DonationOut)
def review_donation(
    donation_id: DonationId, body: ReviewIn, request: Request, db: SessionDep, staff: StaffOnly
) -> DonationOut:
    now = request_now(request)
    donation = offers.get_donation_or_404(db, donation_id)
    return offers.to_out(db, review.review(db, now, staff.user, donation, body.items))


@router.post("/donations/{donation_id}/receive", response_model=DonationOut)
def receive_donation(
    donation_id: DonationId, body: ReceiveIn, request: Request, db: SessionDep, staff: StaffOnly
) -> DonationOut:
    settings = request.app.state.settings
    donation = offers.get_donation_or_404(db, donation_id)
    received = receiving.receive(db, request_now(request),staff.user, settings.holidays, donation, body.items)
    return offers.to_out(db, received)


@router.get("/donations/{donation_id}/receipt", response_model=ReceiptOut)
def donation_receipt(donation_id: DonationId, db: SessionDep, principal: CurrentPrincipal) -> ReceiptOut:
    donation = offers.get_donation_or_404(db, donation_id)
    _require_own(db, principal, donation, hide=True)
    return receiving.receipt(db, donation)
