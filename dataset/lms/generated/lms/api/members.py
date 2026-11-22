"""Member endpoints (section 7.3)."""

from __future__ import annotations

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Query

from lms.auth.deps import CurrentPrincipal, StaffOnly, ensure_own_or_staff
from lms.core.context import HolidaysDep, NowDep, PathId, TodayDep
from lms.core.db import SessionDep
from lms.core.errors import NotFound
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

_OWN_RECORD_ONLY = "Only your own member record can be accessed"


@router.post("", response_model=MemberOut, status_code=201)
def register_member(body: MemberCreateIn, now: NowDep, db: SessionDep, staff: StaffOnly) -> MemberOut:
    member = service.register_member(db, now, staff.user, **body.model_dump())
    return member_out(member, now.date())


@router.get("", response_model=Page[MemberOut])
def list_members(
    day: TodayDep,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    q: Annotated[str | None, Query()] = None,
    membership_type: Annotated[MembershipTypeName | None, Query()] = None,
    status: Annotated[MemberStatus | None, Query()] = None,
    home_branch_id: Annotated[int | None, Query()] = None,
    membership_valid: Annotated[bool | None, Query()] = None,
) -> Page[MemberOut]:
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
def get_own_member(day: TodayDep, db: SessionDep, principal: CurrentPrincipal) -> MemberOut:
    member_id = principal.user.member_id
    member = db.get(Member, member_id) if member_id is not None else None
    if member is None:
        raise NotFound("The authenticated user has no member record", details={"resource": "member"})
    return member_out(member, day)


@router.get("/{member_id}", response_model=MemberOut)
def get_member(member_id: PathId, day: TodayDep, db: SessionDep, principal: CurrentPrincipal) -> MemberOut:
    member = service.get_member_or_404(db, member_id)
    ensure_own_or_staff(principal, member.id, _OWN_RECORD_ONLY)
    return member_out(member, day)


@router.patch("/{member_id}", response_model=MemberOut)
def update_member(member_id: PathId, body: MemberPatchIn, now: NowDep, db: SessionDep, staff: StaffOnly) -> MemberOut:
    member = service.get_member_or_404(db, member_id)
    return member_out(service.update_member(db, now, staff.user, member, body.provided_fields()), now.date())


@router.post("/{member_id}/renew-membership", response_model=MemberOut)
def renew_membership(member_id: PathId, now: NowDep, db: SessionDep, staff: StaffOnly) -> MemberOut:
    member = service.get_member_or_404(db, member_id)
    return member_out(service.renew_membership(db, now, staff.user, member), now.date())


@router.post("/{member_id}/deactivate", response_model=MemberOut)
def deactivate_member(
    member_id: PathId, now: NowDep, holidays: HolidaysDep, db: SessionDep, staff: StaffOnly
) -> MemberOut:
    member = service.get_member_or_404(db, member_id)
    return member_out(service.deactivate_member(db, now, staff.user, holidays, member), now.date())


@router.post("/{member_id}/activate", response_model=MemberOut)
def activate_member(member_id: PathId, now: NowDep, db: SessionDep, staff: StaffOnly) -> MemberOut:
    member = service.get_member_or_404(db, member_id)
    return member_out(service.activate_member(db, now, staff.user, member), now.date())


@router.get("/{member_id}/summary", response_model=MemberSummaryOut)
def member_summary(
    member_id: PathId, day: TodayDep, holidays: HolidaysDep, db: SessionDep, principal: CurrentPrincipal
) -> MemberSummaryOut:
    member = service.get_member_or_404(db, member_id)
    ensure_own_or_staff(principal, member.id, _OWN_RECORD_ONLY)
    activity = service.member_activity(db, member, day, holidays)
    reasons = service.borrowing_blockers(member, activity, day)
    return MemberSummaryOut(
        member=member_out(member, day),
        open_loans=activity.open_loans,
        overdue_loans=activity.overdue_loans,
        active_reservations=activity.active_reservations,
        balance=balance_out(activity.outstanding_fees, activity.accrued_late_fees),
        borrowing=BorrowingOut(eligible=not reasons, reasons=reasons),
    )
