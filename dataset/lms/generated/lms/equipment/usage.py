"""Usage report (LIB-EQ-40), the equipment figures of the member summary (LIB-EQ-37) and the effects of
member deactivation (LIB-EQ-35)."""

from __future__ import annotations

import datetime
from collections import defaultdict
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.money import ZERO, format_amount
from lms.equipment.accrual import count_overdue
from lms.equipment.models import EquipmentLoan, EquipmentReservation, EquipmentType
from lms.equipment.schemas import EquipmentSummaryOut, EquipmentUsageOut
from lms.fines.models import Fee


def member_summary(db: Session, now: datetime.datetime, member_id: int) -> EquipmentSummaryOut:
    open_loans = db.scalar(
        sa.select(sa.func.count()).select_from(EquipmentLoan).where(
            EquipmentLoan.member_id == member_id, EquipmentLoan.status == "open"
        )
    )
    booked = db.scalar(
        sa.select(sa.func.count()).select_from(EquipmentReservation).where(
            EquipmentReservation.member_id == member_id, EquipmentReservation.status == "booked"
        )
    )
    return EquipmentSummaryOut(
        open_loans=open_loans or 0,
        overdue_loans=count_overdue(db, member_id, now),
        booked_reservations=booked or 0,
    )


def has_open_loan(db: Session, member_id: int) -> bool:
    """LIB-EQ-35."""
    stmt = sa.select(EquipmentLoan.id).where(EquipmentLoan.member_id == member_id, EquipmentLoan.status == "open")
    return db.scalar(stmt.limit(1)) is not None


def equipment_usage(
    db: Session, first: datetime.date, last: datetime.date, *, branch_id: int | None = None
) -> list[EquipmentUsageOut]:
    """One item per type, ordered by code."""

    def in_range(moment: datetime.datetime | None) -> bool:
        return moment is not None and first <= moment.date() <= last

    loans_stmt = sa.select(EquipmentLoan)
    reservations_stmt = sa.select(EquipmentReservation)
    if branch_id is not None:
        loans_stmt = loans_stmt.where(EquipmentLoan.branch_id == branch_id)
        reservations_stmt = reservations_stmt.where(EquipmentReservation.branch_id == branch_id)

    counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    loan_type: dict[int, int] = {}
    for loan in db.scalars(loans_stmt):
        loan_type[loan.id] = loan.type_id
        c = counts[loan.type_id]
        if in_range(loan.loaned_at):
            c["loans"] += 1
        if loan.status == "returned" and in_range(loan.returned_at):
            if (loan.late_hours or 0) > 0:
                c["late_returns"] += 1
                c["late_hours"] += loan.late_hours or 0
            if loan.return_condition == "damaged":
                c["damaged_returns"] += 1
        if loan.status == "lost" and in_range(loan.closed_at):
            c["lost"] += 1
    for reservation in db.scalars(reservations_stmt):
        if in_range(reservation.starts_at):
            c = counts[reservation.type_id]
            c["reservations"] += 1
            if reservation.status == "expired":
                c["expired_reservations"] += 1

    fees: dict[int, Decimal] = defaultdict(lambda: ZERO)
    stmt = sa.select(Fee).where(Fee.equipment_loan_id.is_not(None), Fee.created_on >= first, Fee.created_on <= last)
    for fee in db.scalars(stmt):
        type_id = loan_type.get(fee.equipment_loan_id)  # type: ignore[arg-type]
        if type_id is not None:
            fees[type_id] += fee.amount

    items = []
    for equipment_type in db.scalars(sa.select(EquipmentType).order_by(EquipmentType.code, EquipmentType.id)):
        c = counts[equipment_type.id]
        items.append(
            EquipmentUsageOut(
                type_id=equipment_type.id,
                type_code=equipment_type.code,
                loans=c["loans"],
                late_returns=c["late_returns"],
                late_hours=c["late_hours"],
                damaged_returns=c["damaged_returns"],
                lost=c["lost"],
                reservations=c["reservations"],
                expired_reservations=c["expired_reservations"],
                fees_created=format_amount(fees[equipment_type.id]),
            )
        )
    return items
