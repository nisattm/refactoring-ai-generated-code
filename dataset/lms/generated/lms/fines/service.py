"""Business logic of module 7: fees and payments (LIB-FEE-01 to LIB-FEE-11)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.core.calendar import working_days_between
from lms.core.errors import Conflict, NotFound
from lms.core.money import ZERO, format_amount, quantize
from lms.fines.models import Fee, Payment, PaymentAllocation
from lms.loans.models import Loan
from lms.notifications.service import notify_fee_created, notify_fee_waived, notify_payment_received

LATE_FEE_CAP = Decimal("100.00")
LOST_PROCESSING_FEE = Decimal("25.00")


def get_fee_or_404(db: Session, fee_id: int) -> Fee:
    fee = db.get(Fee, fee_id)
    if fee is None:
        raise NotFound(f"Fee {fee_id} does not exist", details={"resource": "fee", "id": fee_id})
    return fee


# --- amounts --------------------------------------------------------------------


def late_days_between(due_date: datetime.date, until: datetime.date, holidays: Container[datetime.date]) -> int:
    """LIB-LOAN-10: working days between the due date and ``until``."""
    return working_days_between(due_date, until, holidays)


def late_fee_amount(late_days: int, daily_fee: Decimal) -> Decimal:
    """LIB-FEE-02: ``min(late_days × daily_fee, 100.00)``, rounded once."""
    if late_days <= 0:
        return ZERO
    return quantize(min(late_days * daily_fee, LATE_FEE_CAP))


def accrued_late_fee(loan: Loan, today: datetime.date, holidays: Container[datetime.date]) -> Decimal:
    """LIB-FEE-02: the fee an open loan has accrued so far (``0.00`` while not overdue)."""
    return late_fee_amount(late_days_between(loan.due_date, today, holidays), loan.daily_fee)


def outstanding_fees(db: Session, member_id: int) -> Decimal:
    """Sum of ``outstanding`` of the member's open fees."""
    fees = db.scalars(sa.select(Fee).where(Fee.member_id == member_id, Fee.status == "open"))
    return sum((f.outstanding for f in fees), ZERO)


def accrued_late_fees(db: Session, member_id: int, today: datetime.date, holidays: Container[datetime.date]) -> Decimal:
    """Sum of ``accrued_late_fee`` of the member's open overdue loans."""
    loans = db.scalars(
        sa.select(Loan).where(Loan.member_id == member_id, Loan.status == "open", Loan.due_date < today)
    )
    return sum((accrued_late_fee(loan, today, holidays) for loan in loans), ZERO)


# --- fees -----------------------------------------------------------------------


def create_fee(
    db: Session,
    now: datetime.datetime,
    actor: User,
    *,
    member_id: int,
    loan_id: int | None,
    kind: str,
    amount: Decimal,
) -> Fee:
    """Create an open fee (LIB-FEE-02 to LIB-FEE-04). ``amount`` is already rounded."""
    fee = Fee(
        member_id=member_id,
        loan_id=loan_id,
        kind=kind,
        amount=amount,
        paid_amount=ZERO,
        status="open",
        created_on=now.date(),
    )
    db.add(fee)
    db.flush()
    record(
        db,
        at=now,
        event="fee_created",
        actor_user_id=actor.id,
        entity_type="fee",
        entity_id=fee.id,
        details={"member_id": member_id, "loan_id": loan_id, "kind": kind, "amount": format_amount(amount)},
    )
    notify_fee_created(db, now, fee)
    return fee


def record_payment(
    db: Session,
    now: datetime.datetime,
    actor: User,
    member_id: int,
    amount: Decimal,
    method: str,
) -> tuple[Payment, list[tuple[int, Decimal]]]:
    """LIB-FEE-05, LIB-FEE-06. ``amount`` is already known to be greater than zero."""
    outstanding = outstanding_fees(db, member_id)
    if amount > outstanding:
        raise Conflict(
            "The payment exceeds the outstanding fees",
            code="PAYMENT_EXCEEDS_BALANCE",
            details={"outstanding_fees": format_amount(outstanding)},
        )
    payment = Payment(member_id=member_id, amount=amount, method=method, received_by=actor.id, paid_at=now)
    db.add(payment)
    db.flush()

    open_fees = db.scalars(
        sa.select(Fee).where(Fee.member_id == member_id, Fee.status == "open").order_by(Fee.created_on, Fee.id)
    )
    remaining = amount
    allocations: list[tuple[int, Decimal]] = []
    for fee in open_fees:
        if remaining <= ZERO:
            break
        share = min(remaining, fee.outstanding)
        fee.paid_amount += share
        if fee.paid_amount == fee.amount:
            fee.status = "paid"
        remaining -= share
        allocations.append((fee.id, share))
        db.add(PaymentAllocation(payment_id=payment.id, fee_id=fee.id, position=len(allocations), amount=share))
    db.flush()
    record(
        db,
        at=now,
        event="payment_received",
        actor_user_id=actor.id,
        entity_type="payment",
        entity_id=payment.id,
        details={
            "member_id": member_id,
            "amount": format_amount(amount),
            "method": method,
            "allocations": [{"fee_id": f, "amount": format_amount(a)} for f, a in allocations],
        },
    )
    notify_payment_received(db, now, member_id, amount)
    return payment, allocations


def payment_allocations(db: Session, payment_id: int) -> list[tuple[int, Decimal]]:
    rows = db.execute(
        sa.select(PaymentAllocation.fee_id, PaymentAllocation.amount)
        .where(PaymentAllocation.payment_id == payment_id)
        .order_by(PaymentAllocation.position)
    )
    return [(fee_id, amount) for fee_id, amount in rows]


def waive_fee(db: Session, now: datetime.datetime, actor: User, fee: Fee, reason: str) -> Fee:
    """LIB-FEE-07: the outstanding part is waived; amounts already paid stay paid."""
    if fee.status != "open":
        raise Conflict("The fee is not open", code="FEE_NOT_OPEN", details={"id": fee.id, "status": fee.status})
    waived_amount = fee.outstanding
    fee.status = "waived"
    fee.waived_by = actor.id
    fee.waived_at = now
    fee.waive_reason = reason
    record(
        db,
        at=now,
        event="fee_waived",
        actor_user_id=actor.id,
        entity_type="fee",
        entity_id=fee.id,
        details={"member_id": fee.member_id, "reason": reason, "waived_amount": format_amount(waived_amount)},
    )
    notify_fee_waived(db, now, fee, waived_amount)
    return fee
