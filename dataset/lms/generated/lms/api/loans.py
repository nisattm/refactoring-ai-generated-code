"""Loan endpoints (section 9.2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from lms.auth.deps import CurrentPrincipal, StaffOnly, ensure_own_or_staff
from lms.core.context import HolidaysDep, NowDep, PathId, TodayDep
from lms.core.db import SessionDep
from lms.core.pagination import Page, PageDep, paginate
from lms.core.params import optional_date
from lms.loans import service
from lms.loans.schemas import LoanCreateIn, LoanOut, LoanStatus, ReturnIn, loan_out
from lms.members.service import get_member_or_404

router = APIRouter(tags=["loans"])

_OWN_LOANS_ONLY = "Only your own loans can be accessed"


@router.post("/loans", response_model=LoanOut, status_code=201)
def lend(body: LoanCreateIn, now: NowDep, holidays: HolidaysDep, db: SessionDep, staff: StaffOnly) -> LoanOut:
    body.check()
    loan = service.lend(
        db, now, staff.user, holidays, member_id=body.member_id, copy_id=body.copy_id, barcode=body.barcode
    )
    return loan_out(loan, now.date(), holidays)


@router.get("/loans", response_model=Page[LoanOut])
def list_loans(
    day: TodayDep,
    holidays: HolidaysDep,
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    member_id: Annotated[int | None, Query()] = None,
    copy_id: Annotated[int | None, Query()] = None,
    book_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    status: Annotated[LoanStatus | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
    due_before: Annotated[str | None, Query()] = None,
) -> Page[LoanOut]:
    stmt = service.loan_list_stmt(
        day,
        member_id=member_id,
        copy_id=copy_id,
        book_id=book_id,
        branch_id=branch_id,
        status=status,
        overdue=overdue,
        due_before=optional_date("due_before", due_before),
    )
    return paginate(db, stmt, page, lambda loan: loan_out(loan, day, holidays))


@router.get("/loans/{loan_id}", response_model=LoanOut)
def get_loan(loan_id: PathId, day: TodayDep, holidays: HolidaysDep, db: SessionDep, principal: CurrentPrincipal) -> LoanOut:
    loan = service.get_loan_or_404(db, loan_id)
    ensure_own_or_staff(principal, loan.member_id, _OWN_LOANS_ONLY)
    return loan_out(loan, day, holidays)


@router.get("/members/{member_id}/loans", response_model=Page[LoanOut])
def list_member_loans(
    member_id: PathId,
    day: TodayDep,
    holidays: HolidaysDep,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    copy_id: Annotated[int | None, Query()] = None,
    book_id: Annotated[int | None, Query()] = None,
    branch_id: Annotated[int | None, Query()] = None,
    status: Annotated[LoanStatus | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
    due_before: Annotated[str | None, Query()] = None,
) -> Page[LoanOut]:
    member = get_member_or_404(db, member_id)
    ensure_own_or_staff(principal, member.id, _OWN_LOANS_ONLY)
    stmt = service.loan_list_stmt(
        day,
        member_id=member.id,
        copy_id=copy_id,
        book_id=book_id,
        branch_id=branch_id,
        status=status,
        overdue=overdue,
        due_before=optional_date("due_before", due_before),
    )
    return paginate(db, stmt, page, lambda loan: loan_out(loan, day, holidays))


@router.post("/loans/{loan_id}/renew", response_model=LoanOut)
def renew_loan(
    loan_id: PathId, now: NowDep, holidays: HolidaysDep, db: SessionDep, principal: CurrentPrincipal
) -> LoanOut:
    loan = service.get_loan_or_404(db, loan_id)
    ensure_own_or_staff(principal, loan.member_id, _OWN_LOANS_ONLY)
    return loan_out(service.renew(db, now, principal.user, holidays, loan), now.date(), holidays)


@router.post("/loans/{loan_id}/return", response_model=LoanOut)
def return_loan(
    loan_id: PathId, body: ReturnIn, now: NowDep, holidays: HolidaysDep, db: SessionDep, staff: StaffOnly
) -> LoanOut:
    body.check()
    loan = service.get_loan_or_404(db, loan_id)
    service.return_loan(
        db, now, staff.user, holidays, loan,
        branch_id=body.branch_id, condition=body.condition, damage_fee=body.damage_fee,
    )
    return loan_out(loan, now.date(), holidays)


@router.post("/loans/{loan_id}/report-lost", response_model=LoanOut)
def report_lost(loan_id: PathId, now: NowDep, holidays: HolidaysDep, db: SessionDep, staff: StaffOnly) -> LoanOut:
    loan = service.report_lost(db, now, staff.user, holidays, service.get_loan_or_404(db, loan_id))
    return loan_out(loan, now.date(), holidays)
