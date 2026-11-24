"""Overdue state and accrued late fees of open reserve loans (LIB-CRS-29, LIB-CRS-36, LIB-CRS-37).

Kept free of imports from other business modules so that module 7 (fines) and module 3 (members) can use it.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.money import ZERO
from lms.courses.models import ReserveLoan
from lms.courses.rules import late_fee_amount, late_minutes_between


def is_overdue(loan: ReserveLoan, now: datetime.datetime) -> bool:
    return loan.status == "open" and now > loan.due_at


def accrued_late_fee(loan: ReserveLoan, now: datetime.datetime) -> Decimal:
    """LIB-CRS-29 with ``now`` as the closing time; zero for a closed loan."""
    if loan.status != "open":
        return ZERO
    return late_fee_amount(loan.loan_period, late_minutes_between(loan.due_at, now))


def overdue_open_loans(db: Session, member_id: int, now: datetime.datetime) -> list[ReserveLoan]:
    stmt = (
        sa.select(ReserveLoan)
        .where(ReserveLoan.member_id == member_id, ReserveLoan.status == "open", ReserveLoan.due_at < now)
        .order_by(ReserveLoan.id)
    )
    return list(db.scalars(stmt))


def accrued_reserve_late_fees(db: Session, member_id: int, now: datetime.datetime) -> Decimal:
    """Sum of ``accrued_late_fee`` of the member's overdue open reserve loans (LIB-CRS-36)."""
    return sum((accrued_late_fee(loan, now) for loan in overdue_open_loans(db, member_id, now)), ZERO)


def count_overdue(db: Session, member_id: int, now: datetime.datetime) -> int:
    stmt = sa.select(sa.func.count()).select_from(ReserveLoan).where(
        ReserveLoan.member_id == member_id, ReserveLoan.status == "open", ReserveLoan.due_at < now
    )
    return db.scalar(stmt) or 0


def count_open(db: Session, member_id: int) -> int:
    stmt = sa.select(sa.func.count()).select_from(ReserveLoan).where(
        ReserveLoan.member_id == member_id, ReserveLoan.status == "open"
    )
    return db.scalar(stmt) or 0
