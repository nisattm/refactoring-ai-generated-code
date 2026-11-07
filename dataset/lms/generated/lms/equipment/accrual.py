"""Accrued late fees and overdue state of open equipment loans (LIB-EQ-14, LIB-EQ-16, LIB-EQ-23).

Kept free of imports from other business modules so that module 7 (fines) can use it.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.money import ZERO
from lms.equipment.models import EquipmentItem, EquipmentLoan
from lms.equipment.rules import GRACE, late_fee_amount, late_hours_between


def overdue_open_loans(db: Session, member_id: int, now: datetime.datetime) -> list[EquipmentLoan]:
    stmt = (
        sa.select(EquipmentLoan)
        .where(EquipmentLoan.member_id == member_id, EquipmentLoan.status == "open", EquipmentLoan.due_at < now - GRACE)
        .order_by(EquipmentLoan.id)
    )
    return list(db.scalars(stmt))


def accrued_late_fee(db: Session, loan: EquipmentLoan, now: datetime.datetime) -> Decimal:
    """LIB-EQ-23 for an open loan as if it were returned now; zero for a closed loan."""
    if loan.status != "open":
        return ZERO
    item = db.get(EquipmentItem, loan.item_id)
    assert item is not None
    return late_fee_amount(late_hours_between(loan.due_at, now), loan.hourly_late_fee, item.value)


def accrued_equipment_late_fees(db: Session, member_id: int, now: datetime.datetime) -> Decimal:
    """Sum of ``accrued_late_fee`` of the member's open overdue equipment loans (LIB-EQ-14)."""
    return sum((accrued_late_fee(db, loan, now) for loan in overdue_open_loans(db, member_id, now)), ZERO)


def count_overdue(db: Session, member_id: int, now: datetime.datetime) -> int:
    stmt = sa.select(sa.func.count()).select_from(EquipmentLoan).where(
        EquipmentLoan.member_id == member_id, EquipmentLoan.status == "open", EquipmentLoan.due_at < now - GRACE
    )
    return db.scalar(stmt) or 0
