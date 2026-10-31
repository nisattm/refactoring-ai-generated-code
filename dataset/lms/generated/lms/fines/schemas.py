"""Balance representation (LIB-FEE-10). The fee and payment schemas are added with module 7."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from lms.core.money import ZERO, format_amount

BLOCKING_DEBT = Decimal("50.00")


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
