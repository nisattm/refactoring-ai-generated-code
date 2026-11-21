"""Member endpoints (section 7.3)."""

from __future__ import annotations

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, Request

from lms.api.common import now_of, provided_fields, require_own_member, settings_of, today_of
from lms.auth.deps import CurrentPrincipal, StaffOnly
from lms.core.db import SessionDep
from lms.core.errors import NotFound
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.core.text import normalize, search_needle
from lms.fines.schemas import balance_out
from lms.members import service
from lms.members.models import Member
from lms.members.schemas import (
    BorrowingOut,
    MemberCreateIn,
    MemberOut,
    MemberPatchIn,
    MemberStatus,
    MembershipTypeName,
    MemberSummaryOut,
    member_out,
)

router = APIRouter(prefix="/members", tags=["members"])

MemberId = Annotated[int, Path(ge=1)]


@router.post("", response_model=MemberOut, status_code=201)
def register_member(body: MemberCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> MemberOut:
    now = now_of(request)
    member = service.register_member(db, now, staff.user, **body.model_dump())
    return member_out(member, now.date())


@router.get("", response_model=Page[MemberOut])
def list_members(
    request: Request,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    q: Annotated[str | None, Query()] = None,
    membership_type: Annotated[MembershipTypeName | None, Query()] = None,
    status: Annotated[MemberStatus | None, Query()] = None,
    home_branch_id: Annotated[int | None, Query()] = None,
    membership_valid: Annotated[bool | None, Query()] = None,
) -> Page[MemberOut]:
    day = today_of(request)
    stmt = sa.select(Member).order_by(Member.id)
    if membership_type is not None:
        stmt = stmt.where(Member.membership_type == membership_type)
    if status is not None:
        stmt = stmt.where(Member.status == status)
    if home_branch_id is not None:
        stmt = stmt.where(Member.home_branch_id == home_branch_id)
    if membership_valid is not None:
        valid = sa.and_(Member.status == "active", Member.valid_until >= day)
        stmt = stmt.where(valid if membership_valid else sa.not_(valid))
    needle = search_needle(q)
    if not needle:
        return paginate(db, stmt, page, lambda m: member_out(m, day))
    # Case-insensitive matching follows LIB-COM-30, which SQLite cannot do for Turkish letters.
    matches = [
        member_out(m, day)
        for m in db.scalars(stmt)
        if any(
            needle in normalize(value)
            for value in (m.full_name, m.email, m.member_no, m.university_id)
            if value is not None
        )
    ]
    return paginate_sequence(matches, page)


@router.get("/me", response_model=MemberOut)
def get_own_member(request: Request, db: SessionDep, principal: CurrentPrincipal) -> MemberOut:
    member_id = principal.user.member_id
    member = db.get(Member, member_id) if member_id is not None else None
    if member is None:
        raise NotFound("The authenticated user has no member record", details={"resource": "member"})
    return member_out(member, today_of(request))


@router.get("/{member_id}", response_model=MemberOut)
def get_member(member_id: MemberId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> MemberOut:
    member = service.get_member_or_404(db, member_id)
    require_own_member(principal, member.id, "member record")
    return member_out(member, today_of(request))


@router.patch("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: MemberId, body: MemberPatchIn, request: Request, db: SessionDep, staff: StaffOnly
) -> MemberOut:
    now = now_of(request)
    member = service.get_member_or_404(db, member_id)
    return member_out(service.update_member(db, now, staff.user, member, provided_fields(body)), now.date())


@router.post("/{member_id}/renew-membership", response_model=MemberOut)
def renew_membership(member_id: MemberId, request: Request, db: SessionDep, staff: StaffOnly) -> MemberOut:
    now = now_of(request)
    member = service.get_member_or_404(db, member_id)
    return member_out(service.renew_membership(db, now, staff.user, member), now.date())


@router.post("/{member_id}/deactivate", response_model=MemberOut)
def deactivate_member(member_id: MemberId, request: Request, db: SessionDep, staff: StaffOnly) -> MemberOut:
    now = now_of(request)
    member = service.get_member_or_404(db, member_id)
    holidays = settings_of(request).holidays
    return member_out(service.deactivate_member(db, now, staff.user, holidays, member), now.date())


@router.post("/{member_id}/activate", response_model=MemberOut)
def activate_member(member_id: MemberId, request: Request, db: SessionDep, staff: StaffOnly) -> MemberOut:
    now = now_of(request)
    member = service.get_member_or_404(db, member_id)
    return member_out(service.activate_member(db, now, staff.user, member), now.date())


@router.get("/{member_id}/summary", response_model=MemberSummaryOut)
def member_summary(member_id: MemberId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> MemberSummaryOut:
    day = today_of(request)
    member = service.get_member_or_404(db, member_id)
    require_own_member(principal, member.id, "member record")
    activity = service.member_activity(db, member, day, settings_of(request).holidays)
    reasons = service.borrowing_blockers(member, activity, day)
    return MemberSummaryOut(
        member=member_out(member, day),
        open_loans=activity.open_loans,
        overdue_loans=activity.overdue_loans,
        active_reservations=activity.active_reservations,
        balance=balance_out(activity.outstanding_fees, activity.accrued_late_fees),
        borrowing=BorrowingOut(eligible=not reasons, reasons=reasons),
    )
