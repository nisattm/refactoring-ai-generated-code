"""Loan endpoints (section 9.2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy.orm import Session

from lms.api.common import IdPath, optional_date, settings_of, today_of
from lms.auth.deps import CurrentPrincipal, StaffOnly, require_own_or_staff
from lms.core.clock import local_now
from lms.core.db import SessionDep
from lms.core.pagination import Page, PageDep, PageParams, paginate
from lms.loans import service
from lms.loans.schemas import LoanCreateIn, LoanOut, LoanStatus, ReturnIn, loan_out
from lms.members.service import get_member_or_404

router = APIRouter(tags=["loans"])


def _loan_page(
    db: Session,
    request: Request,
    page: PageParams,
    *,
    member_id: int | None,
    copy_id: int | None,
    book_id: int | None,
    branch_id: int | None,
    status: str | None,
    overdue: bool | None,
    due_before: str | None,
) -> Page[LoanOut]:
    holidays = settings_of(request).holidays
    day = today_of(request)
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


@router.post("/loans", response_model=LoanOut, status_code=201)
def lend(body: LoanCreateIn, request: Request, db: SessionDep, staff: StaffOnly) -> LoanOut:
    body.check()
    settings = settings_of(request)
    now = local_now(settings.clock)
    loan = service.lend(
        db, now, staff.user, settings.holidays, member_id=body.member_id, copy_id=body.copy_id, barcode=body.barcode
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
    return _loan_page(
        db,
        request,
        page,
        member_id=member_id,
        copy_id=copy_id,
        book_id=book_id,
        branch_id=branch_id,
        status=status,
        overdue=overdue,
        due_before=due_before,
    )


@router.get("/loans/{loan_id}", response_model=LoanOut)
def get_loan(loan_id: IdPath, request: Request, db: SessionDep, principal: CurrentPrincipal) -> LoanOut:
    loan = service.get_loan_or_404(db, loan_id)
    require_own_or_staff(principal, loan.member_id, "loans")
    return loan_out(loan, today_of(request), settings_of(request).holidays)


@router.get("/members/{member_id}/loans", response_model=Page[LoanOut])
def list_member_loans(
    member_id: IdPath,
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
    member = get_member_or_404(db, member_id)
    require_own_or_staff(principal, member.id, "loans")
    return _loan_page(
        db,
        request,
        page,
        member_id=member.id,
        copy_id=copy_id,
        book_id=book_id,
        branch_id=branch_id,
        status=status,
        overdue=overdue,
        due_before=due_before,
    )


@router.post("/loans/{loan_id}/renew", response_model=LoanOut)
def renew_loan(loan_id: IdPath, request: Request, db: SessionDep, principal: CurrentPrincipal) -> LoanOut:
    settings = settings_of(request)
    now = local_now(settings.clock)
    loan = service.get_loan_or_404(db, loan_id)
    require_own_or_staff(principal, loan.member_id, "loans")
    return loan_out(service.renew(db, now, principal.user, settings.holidays, loan), now.date(), settings.holidays)


@router.post("/loans/{loan_id}/return", response_model=LoanOut)
def return_loan(loan_id: IdPath, body: ReturnIn, request: Request, db: SessionDep, staff: StaffOnly) -> LoanOut:
    body.check()
    settings = settings_of(request)
    now = local_now(settings.clock)
    loan = service.get_loan_or_404(db, loan_id)
    service.return_loan(
        db, now, staff.user, settings.holidays, loan,
        branch_id=body.branch_id, condition=body.condition, damage_fee=body.damage_fee,
    )
    return loan_out(loan, now.date(), settings.holidays)


@router.post("/loans/{loan_id}/report-lost", response_model=LoanOut)
def report_lost(loan_id: IdPath, request: Request, db: SessionDep, staff: StaffOnly) -> LoanOut:
    settings = settings_of(request)
    now = local_now(settings.clock)
    loan = service.report_lost(db, now, staff.user, settings.holidays, service.get_loan_or_404(db, loan_id))
    return loan_out(loan, now.date(), settings.holidays)
