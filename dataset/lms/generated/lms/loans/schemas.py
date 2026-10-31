"""Request and response schemas of module 5 (section 9)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, StrictInt

from lms.core.errors import ValidationFailed
from lms.core.money import ZERO, Money, format_amount
from lms.core.schemas import RequestModel
from lms.fines.service import accrued_late_fee, late_fee_amount
from lms.loans.models import Loan

LoanStatus = Literal["open", "returned", "lost"]
ReturnCondition = Literal["good", "damaged"]


class LoanCreateIn(RequestModel):
    member_id: StrictInt
    copy_id: StrictInt | None = None
    barcode: str | None = None

    def check(self) -> None:
        """LIB-LOAN-01: exactly one of ``copy_id`` and ``barcode``."""
        if (self.copy_id is None) == (self.barcode is None):
            raise ValidationFailed.single("copy_id", "exactly one of copy_id and barcode is required")
        if self.barcode is not None and not self.barcode:
            raise ValidationFailed.single("barcode", "barcode must not be empty")


class ReturnIn(RequestModel):
    branch_id: StrictInt
    condition: ReturnCondition
    damage_fee: Money | None = None

    def check(self) -> None:
        """LIB-LOAN-11: ``damage_fee`` is required (> 0.00) for a damaged return and absent otherwise."""
        if self.condition == "good":
            if self.damage_fee is not None:
                raise ValidationFailed.single("damage_fee", "damage_fee must be absent when the condition is good")
        elif self.damage_fee is None or self.damage_fee <= ZERO:
            raise ValidationFailed.single(
                "damage_fee", "damage_fee greater than 0.00 is required when the condition is damaged"
            )


class LoanOut(BaseModel):
    id: int
    copy_id: int
    member_id: int
    branch_id: int
    loan_date: str
    due_date: str
    loan_period_days: int
    max_renewals: int
    daily_fee: str
    renewal_count: int
    status: str
    returned_on: str | None
    return_branch_id: int | None
    condition_on_return: str | None
    late_days: int | None
    created_by: int
    is_overdue: bool
    accrued_late_fee: str


def is_overdue(loan: Loan, today: datetime.date) -> bool:
    """LIB-LOAN-02."""
    return loan.status == "open" and today > loan.due_date


def loan_out(loan: Loan, today: datetime.date, holidays: Container[datetime.date]) -> LoanOut:
    if loan.status == "open":
        fee: Decimal = accrued_late_fee(loan, today, holidays)
    else:
        fee = late_fee_amount(loan.late_days or 0, loan.daily_fee)
    return LoanOut(
        id=loan.id,
        copy_id=loan.copy_id,
        member_id=loan.member_id,
        branch_id=loan.branch_id,
        loan_date=loan.loan_date.isoformat(),
        due_date=loan.due_date.isoformat(),
        loan_period_days=loan.loan_period_days,
        max_renewals=loan.max_renewals,
        daily_fee=format_amount(loan.daily_fee),
        renewal_count=loan.renewal_count,
        status=loan.status,
        returned_on=loan.returned_on.isoformat() if loan.returned_on is not None else None,
        return_branch_id=loan.return_branch_id,
        condition_on_return=loan.condition_on_return,
        late_days=loan.late_days,
        created_by=loan.created_by,
        is_overdue=is_overdue(loan, today),
        accrued_late_fee=format_amount(fee),
    )
