"""Demand and capacity of a type at a branch (LIB-EQ-27)."""

from __future__ import annotations

import datetime
from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.equipment.models import EquipmentItem, EquipmentLoan, EquipmentReservation
from lms.equipment.rules import (
    COLLECT_LATE,
    FAR_FUTURE,
    GRACE,
    HOLD_EARLY,
    LENDABLE_STATUSES,
)

Interval = tuple[datetime.datetime, datetime.datetime]


def is_expired(reservation: EquipmentReservation, now: datetime.datetime) -> bool:
    """LIB-EQ-31: a ``booked`` reservation more than 30 minutes past its start."""
    return reservation.status == "booked" and now > reservation.starts_at + COLLECT_LATE


def hold_interval(starts_at: datetime.datetime, ends_at: datetime.datetime) -> Interval:
    """The interval during which a reservation holds an item (24.2)."""
    return (starts_at - HOLD_EARLY, ends_at)


def loan_interval(loan: EquipmentLoan, now: datetime.datetime) -> Interval:
    """The interval during which an open loan needs its item (24.2); an overdue loan needs it until closed."""
    if now > loan.due_at + GRACE:
        return (loan.loaned_at, FAR_FUTURE)
    return (loan.loaned_at, loan.due_at + GRACE)


def capacity(db: Session, type_id: int, branch_id: int) -> int:
    """The number of lendable items of the type at the branch."""
    stmt = sa.select(sa.func.count()).select_from(EquipmentItem).where(
        EquipmentItem.type_id == type_id,
        EquipmentItem.branch_id == branch_id,
        EquipmentItem.status.in_(LENDABLE_STATUSES),
    )
    return db.scalar(stmt) or 0


def existing_intervals(
    db: Session,
    type_id: int,
    branch_id: int,
    now: datetime.datetime,
    *,
    exclude_loan_id: int | None = None,
    exclude_reservation_id: int | None = None,
) -> list[Interval]:
    """Intervals of the open loans and the holding reservations of the type at the branch."""
    intervals: list[Interval] = []
    loans = db.scalars(
        sa.select(EquipmentLoan).where(
            EquipmentLoan.type_id == type_id, EquipmentLoan.branch_id == branch_id, EquipmentLoan.status == "open"
        )
    )
    for loan in loans:
        if loan.id != exclude_loan_id:
            intervals.append(loan_interval(loan, now))
    reservations = db.scalars(
        sa.select(EquipmentReservation).where(
            EquipmentReservation.type_id == type_id,
            EquipmentReservation.branch_id == branch_id,
            EquipmentReservation.status == "booked",
        )
    )
    for reservation in reservations:
        if reservation.id != exclude_reservation_id and not is_expired(reservation, now):
            intervals.append(hold_interval(reservation.starts_at, reservation.ends_at))
    return intervals


def demand_at(intervals: Iterable[Interval], t: datetime.datetime) -> int:
    return sum(1 for start, end in intervals if start <= t < end)


def max_demand(intervals: list[Interval], start: datetime.datetime, end: datetime.datetime) -> int:
    """The highest demand at any moment of ``[start, end)``; demand only changes where an interval starts."""
    if start >= end:
        return 0
    points = [start] + [s for s, _ in intervals if start < s < end]
    return max(demand_at(intervals, t) for t in points)


def fits(
    intervals: list[Interval],
    new: Interval,
    cap: int,
    now: datetime.datetime,
) -> bool:
    """LIB-EQ-27: with ``new`` counted, the demand stays within ``cap`` at every moment ``t >= now`` of ``new``."""
    start = max(new[0], now)
    return max_demand(intervals + [new], start, new[1]) <= cap


def survives_removal_of_item(db: Session, item: EquipmentItem, now: datetime.datetime) -> bool:
    """The check of LIB-EQ-08 and LIB-EQ-10: without the item, demand never exceeds capacity from now on."""
    if item.status not in LENDABLE_STATUSES:
        return True
    intervals = existing_intervals(db, item.type_id, item.branch_id, now)
    cap = capacity(db, item.type_id, item.branch_id) - 1
    return max_demand(intervals, now, FAR_FUTURE) <= cap
