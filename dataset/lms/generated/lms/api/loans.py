"""Loan endpoints (section 9.2)."""

from __future__ import annotations

import datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, Request

from lms.api.params import optional_date, require_own_or_staff
from lms.auth.deps import CurrentPrincipal, Principal, StaffOnly
from lms.core.clock import local_now, today
from lms.core.db import SessionDep
from lms.core.pagination import Page, PageDep, paginate
from lms.loans import service
from lms.loans.models import Loan
from lms.loans.schemas import LoanCreateIn, LoanOut, LoanStatus, ReturnIn, loan_out
from lms.members.service import get_member_or_404

router = APIRouter(tags=["loans"])

LoanId = Annotated[int, Path(ge=1)]
MemberId = Annotated[int, Path(ge=1)]


def _own_or_staff(principal: Principal, member_id: int) -> None:
    """LIB-AUTH-25: a member may only address their own loans."""
    require_own_or_staff(principal, member_id, "Only your own loans can be accessed")


def _loan_stmt(
    day: datetime.date,
    due_before: str | None,
    *,
    member_id: int | None,
    copy_id: int | None,
    book_id: int | None,
    branch_id: int | None,
    status: LoanStatus | None,
    overdue: bool | None,
) -> sa.Select[tuple[Loan]]:
    """The filtered loan list shared by ``GET /loans`` and ``GET /members/{id}/loans`` (LIB-LOAN-14)."""
    return service.loan_list_stmt(
        day,
        member_id=member_id,
        copy_id=copy_id,
        book_id=book_id,
        branch_id=branch_id,
        status=status,
        overdue=overdue,
        due_before=optional_date("due_before", due_before),
    )


@router.post("/loans", response_model=LoanOut, status_code=201)
def lend(body: LoanCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> LoanOut:
    body.check()
    settings = request.app.state.settings
    now = local_now(settings.clock)
    loan = service.lend(
        db, now, staff.user, settings.holidays, member_id=body.member_id, card_no=body.card_no, copy_id=body.copy_id, barcode=body.barcode
    )
    return loan_out(loan, now.date(), settings.holidays)


@router.get("/loans", response_model=Page[LoanOut])
def list_loans(
    request: Request,
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
    settings = request.app.state.settings
    day = today(settings.clock)
    stmt = _loan_stmt(
        day,
        due_before,
        member_id=member_id,
        copy_id=copy_id,
        book_id=book_id,
        branch_id=branch_id,
        status=status,
        overdue=overdue,
    )
    return paginate(db, stmt, page, lambda loan: loan_out(loan, day, settings.holidays))


@router.get("/loans/{loan_id}", response_model=LoanOut)
def get_loan(loan_id: LoanId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> LoanOut:
    settings = request.app.state.settings
    loan = service.get_loan_or_404(db, loan_id)
    _own_or_staff(principal, loan.member_id)
    return loan_out(loan, today(settings.clock), settings.holidays)


@router.get("/members/{member_id}/loans", response_model=Page[LoanOut])
def list_member_loans(
    member_id: MemberId,
    request: Request,
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
    settings = request.app.state.settings
    day = today(settings.clock)
    member = get_member_or_404(db, member_id)
    _own_or_staff(principal, member.id)
    stmt = _loan_stmt(
        day,
        due_before,
        member_id=member.id,
        copy_id=copy_id,
        book_id=book_id,
        branch_id=branch_id,
        status=status,
        overdue=overdue,
    )
    return paginate(db, stmt, page, lambda loan: loan_out(loan, day, settings.holidays))


@router.post("/loans/{loan_id}/renew", response_model=LoanOut)
def renew_loan(loan_id: LoanId, request: Request, db: SessionDep, principal: CurrentPrincipal) -> LoanOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    loan = service.get_loan_or_404(db, loan_id)
    _own_or_staff(principal, loan.member_id)
    return loan_out(service.renew(db, now, principal.user, settings.holidays, loan), now.date(), settings.holidays)


@router.post("/loans/{loan_id}/return", response_model=LoanOut)
def return_loan(loan_id: LoanId, body: ReturnIn, request: Request, db: SessionDep, staff: StaffOnly) -> LoanOut:
    body.check()
    settings = request.app.state.settings
    now = local_now(settings.clock)
    loan = service.get_loan_or_404(db, loan_id)
    service.return_loan(
        db, now, staff.user, settings.holidays, loan,
        branch_id=body.branch_id, condition=body.condition, damage_fee=body.damage_fee,
    )
    return loan_out(loan, now.date(), settings.holidays)


@router.post("/loans/{loan_id}/report-lost", response_model=LoanOut)
def report_lost(loan_id: LoanId, request: Request, db: SessionDep, staff: StaffOnly) -> LoanOut:
    settings = request.app.state.settings
    now = local_now(settings.clock)
    loan = service.report_lost(db, now, staff.user, settings.holidays, service.get_loan_or_404(db, loan_id))
    return loan_out(loan, now.date(), settings.holidays)
