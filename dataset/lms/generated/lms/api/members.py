"""Member endpoints (section 7.3)."""

from __future__ import annotations

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, Request

from lms.auth.deps import CurrentPrincipal, Principal, StaffOnly
from lms.core.clock import local_now, today
from lms.core.db import SessionDep
from lms.core.errors import Forbidden, NotFound
from lms.core.pagination import Page, PageDep, paginate, paginate_sequence
from lms.core.text import normalize
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


def _today(request: Request):  # noqa: ANN202
    return today(request.app.state.settings.clock)


def _own_or_staff(principal: Principal, member: Member) -> None:
    """LIB-AUTH-25: a member may only address their own record."""
    if principal.user.role == "member" and principal.user.member_id != member.id:
        raise Forbidden("Only your own member record can be accessed")


@router.post("", response_model=MemberOut, status_code=201)
def register_member(body: MemberCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> MemberOut:
    now = local_now(request.app.state.settings.clock)
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
    day = _today(request)
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
    needle = normalize(q.strip()) if q is not None else ""
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
    return member_out(member, _today(request))


@router.get("/{member_id}", response_model=MemberOut)
def get_member(member_id: MemberId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> MemberOut:
    member = service.get_member_or_404(db, member_id)
    _own_or_staff(principal, member)
    return member_out(member, _today(request))


@router.patch("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: MemberId, body: MemberPatchIn, request: Request, db: SessionDep, staff: StaffOnly
) -> MemberOut:
    now = local_now(request.app.state.settings.clock)
    member = service.get_member_or_404(db, member_id)
    fields = {name: getattr(body, name) for name in body.model_fields_set}
    return member_out(service.update_member(db, now, staff.user, member, fields), now.date())


@router.post("/{member_id}/renew-membership", response_model=MemberOut)
def renew_membership(member_id: MemberId, request: Request, db: SessionDep, _: StaffOnly) -> MemberOut:
    day = _today(request)
    member = service.get_member_or_404(db, member_id)
    return member_out(service.renew_membership(member, day), day)


@router.post("/{member_id}/deactivate", response_model=MemberOut)
def deactivate_member(member_id: MemberId, request: Request, db: SessionDep, _: StaffOnly) -> MemberOut:
    day = _today(request)
    member = service.get_member_or_404(db, member_id)
    return member_out(service.deactivate_member(db, member, day), day)


@router.post("/{member_id}/activate", response_model=MemberOut)
def activate_member(member_id: MemberId, request: Request, db: SessionDep, _: StaffOnly) -> MemberOut:
    member = service.get_member_or_404(db, member_id)
    return member_out(service.activate_member(member), _today(request))


@router.get("/{member_id}/summary", response_model=MemberSummaryOut)
def member_summary(member_id: MemberId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> MemberSummaryOut:
    day = _today(request)
    member = service.get_member_or_404(db, member_id)
    _own_or_staff(principal, member)
    activity = service.member_activity(db, member, day)
    reasons = service.borrowing_blockers(member, activity, day)
    return MemberSummaryOut(
        member=member_out(member, day),
        open_loans=activity.open_loans,
        overdue_loans=activity.overdue_loans,
        active_reservations=activity.active_reservations,
        balance=balance_out(activity.outstanding_fees, activity.accrued_late_fees),
        borrowing=BorrowingOut(eligible=not reasons, reasons=reasons),
    )
