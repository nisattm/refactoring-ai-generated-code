"""Request and response schemas of module 7 (section 11)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from lms.core.money import ZERO, Money, format_amount
from lms.core.schemas import RequestModel
from lms.core.timeutil import format_datetime
from lms.fines.models import Fee, Payment

BLOCKING_DEBT = Decimal("50.00")

FeeKind = Literal["late_fee", "damage_fee", "lost_book", "lost_processing"]
FeeStatus = Literal["open", "paid", "waived"]
PaymentMethod = Literal["cash", "card"]


class BalanceOut(BaseModel):
    outstanding_fees: str
    accrued_late_fees: str
    total_debt: str
    blocked: bool


def balance_out(outstanding_fees: Decimal = ZERO, accrued_late_fees: Decimal = ZERO) -> BalanceOut:
    total = outstanding_fees + accrued_late_fees
    return BalanceOut(
        outstanding_fees=format_amount(outstanding_fees),
        accrued_late_fees=format_amount(accrued_late_fees),
        total_debt=format_amount(total),
        blocked=total >= BLOCKING_DEBT,
    )


class FeeOut(BaseModel):
    id: int
    member_id: int
    loan_id: int | None
    kind: str
    amount: str
    paid_amount: str
    status: str
    created_on: str
    waived_by: int | None
    waived_at: str | None
    waive_reason: str | None
    outstanding: str


def fee_out(fee: Fee) -> FeeOut:
    return FeeOut(
        id=fee.id,
        member_id=fee.member_id,
        loan_id=fee.loan_id,
        kind=fee.kind,
        amount=format_amount(fee.amount),
        paid_amount=format_amount(fee.paid_amount),
        status=fee.status,
        created_on=fee.created_on.isoformat(),
        waived_by=fee.waived_by,
        waived_at=format_datetime(fee.waived_at) if fee.waived_at is not None else None,
        waive_reason=fee.waive_reason,
        outstanding=format_amount(fee.outstanding),
    )


class PaymentIn(RequestModel):
    amount: Money
    method: PaymentMethod

    @field_validator("amount")
    @classmethod
    def _positive(cls, value: Decimal) -> Decimal:
        if value <= ZERO:
            raise ValueError("amount must be greater than 0.00")
        return value


class WaiveIn(RequestModel):
    reason: Annotated[str, Field(min_length=5, max_length=500)]


class AllocationOut(BaseModel):
    fee_id: int
    amount: str


class PaymentOut(BaseModel):
    id: int
    member_id: int
    amount: str
    method: str
    received_by: int
    paid_at: str
    allocations: list[AllocationOut]


def payment_out(payment: Payment, allocations: list[tuple[int, Decimal]]) -> PaymentOut:
    return PaymentOut(
        id=payment.id,
        member_id=payment.member_id,
        amount=format_amount(payment.amount),
        method=payment.method,
        received_by=payment.received_by,
        paid_at=format_datetime(payment.paid_at),
        allocations=[AllocationOut(fee_id=f, amount=format_amount(a)) for f, a in allocations],
    )
