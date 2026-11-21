"""Fee and payment endpoints (section 11.2)."""

from __future__ import annotations

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Query, Request

from lms.api.common import IdPath, now_of, settings_of, today_of
from lms.auth.deps import AdminOnly, CurrentPrincipal, StaffOnly, require_own_or_staff
from lms.core.db import SessionDep, apply_filters
from lms.core.pagination import Page, PageDep, paginate
from lms.fines import service
from lms.fines.models import Fee, Payment
from lms.fines.schemas import (
    BalanceOut,
    FeeKind,
    FeeOut,
    FeeStatus,
    PaymentIn,
    PaymentOut,
    WaiveIn,
    balance_out,
    fee_out,
    payment_out,
)
from lms.members.service import get_member_or_404

router = APIRouter(tags=["fines"])


def _fee_stmt(
    status: str | None, kind: str | None, loan_id: int | None, member_id: int | None
) -> sa.Select[tuple[Fee]]:
    """LIB-FEE-08."""
    return apply_filters(
        sa.select(Fee).order_by(Fee.created_on, Fee.id),
        (Fee.member_id, member_id),
        (Fee.status, status),
        (Fee.kind, kind),
        (Fee.loan_id, loan_id),
    )


@router.get("/members/{member_id}/fees", response_model=Page[FeeOut])
def list_member_fees(
    member_id: IdPath,
    db: SessionDep,
    principal: CurrentPrincipal,
    page: PageDep,
    status: Annotated[FeeStatus | None, Query()] = None,
    kind: Annotated[FeeKind | None, Query()] = None,
    loan_id: Annotated[int | None, Query()] = None,
) -> Page[FeeOut]:
    member = get_member_or_404(db, member_id)
    require_own_or_staff(principal, member.id, "fees and payments")
    return paginate(db, _fee_stmt(status, kind, loan_id, member.id), page, fee_out)


@router.get("/fees", response_model=Page[FeeOut])
def list_fees(
    db: SessionDep,
    _: StaffOnly,
    page: PageDep,
    member_id: Annotated[int | None, Query()] = None,
    status: Annotated[FeeStatus | None, Query()] = None,
    kind: Annotated[FeeKind | None, Query()] = None,
    loan_id: Annotated[int | None, Query()] = None,
) -> Page[FeeOut]:
    return paginate(db, _fee_stmt(status, kind, loan_id, member_id), page, fee_out)


@router.get("/members/{member_id}/balance", response_model=BalanceOut)
def get_balance(member_id: IdPath, request: Request, db: SessionDep, principal: CurrentPrincipal) -> BalanceOut:
    member = get_member_or_404(db, member_id)
    require_own_or_staff(principal, member.id, "fees and payments")
    return balance_out(
        service.outstanding_fees(db, member.id),
        service.accrued_late_fees(db, member.id, today_of(request), settings_of(request).holidays),
    )


@router.post("/members/{member_id}/payments", response_model=PaymentOut, status_code=201)
def record_payment(member_id: IdPath, body: PaymentIn, request: Request, db: SessionDep, staff: StaffOnly) -> PaymentOut:
    now = now_of(request)
    member = get_member_or_404(db, member_id)
    payment, allocations = service.record_payment(db, now, staff.user, member.id, body.amount, body.method)
    return payment_out(payment, allocations)


@router.get("/members/{member_id}/payments", response_model=Page[PaymentOut])
def list_member_payments(
    member_id: IdPath, db: SessionDep, principal: CurrentPrincipal, page: PageDep
) -> Page[PaymentOut]:
    member = get_member_or_404(db, member_id)
    require_own_or_staff(principal, member.id, "fees and payments")
    stmt = sa.select(Payment).where(Payment.member_id == member.id).order_by(Payment.paid_at, Payment.id)
    return paginate(db, stmt, page, lambda p: payment_out(p, service.payment_allocations(db, p.id)))


@router.post("/fees/{fee_id}/waive", response_model=FeeOut)
def waive_fee(fee_id: IdPath, body: WaiveIn, request: Request, db: SessionDep, admin: AdminOnly) -> FeeOut:
    now = now_of(request)
    fee = service.get_fee_or_404(db, fee_id)
    return fee_out(service.waive_fee(db, now, admin.user, fee, body.reason))
