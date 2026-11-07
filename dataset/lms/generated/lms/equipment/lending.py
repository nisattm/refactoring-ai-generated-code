"""Lending, extension, return and loss (LIB-EQ-12 to LIB-EQ-25)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.errors import Conflict, NotFound, reference_not_found
from lms.core.money import ZERO, format_amount
from lms.core.timeutil import format_datetime
from lms.equipment import capacity
from lms.equipment.accrual import accrued_late_fee, overdue_open_loans
from lms.equipment.inventory import get_type_or_404, has_valid_training
from lms.equipment.models import EquipmentItem, EquipmentLoan, EquipmentReservation, EquipmentType
from lms.equipment.rules import (
    COLLECT_LATE,
    DEBT_BLOCK,
    EQUIPMENT_RULES,
    GRACE,
    HOLD_EARLY,
    desk_open,
    due_at_from,
    is_overdue,
    late_fee_amount,
    late_hours_between,
    next_desk_opening,
)
from lms.fines import service as fines
from lms.loans.models import Loan
from lms.members.models import Member
from lms.notifications.service import notify_equipment


def get_loan_or_404(db: Session, loan_id: int) -> EquipmentLoan:
    loan = db.get(EquipmentLoan, loan_id)
    if loan is None:
        raise NotFound(f"Equipment loan {loan_id} does not exist", details={"resource": "equipment_loan", "id": loan_id})
    return loan


def error(code: str, message: str, **details: Any) -> Conflict:
    return Conflict(message, code=code, details=details)


def loan_with_labels(db: Session, loan: EquipmentLoan) -> tuple[str, str]:
    """The asset tag and the type code of the loan's item."""
    row = db.execute(
        sa.select(EquipmentItem.asset_tag, EquipmentType.code)
        .join(EquipmentType, EquipmentType.id == EquipmentItem.type_id)
        .where(EquipmentItem.id == loan.item_id)
    ).one()
    return row[0], row[1]


def open_loans_of(db: Session, member_id: int, type_id: int | None = None) -> int:
    stmt = sa.select(sa.func.count()).select_from(EquipmentLoan).where(
        EquipmentLoan.member_id == member_id, EquipmentLoan.status == "open"
    )
    if type_id is not None:
        stmt = stmt.where(EquipmentLoan.type_id == type_id)
    return db.scalar(stmt) or 0


def total_debt(db: Session, member_id: int, now: datetime.datetime, holidays: Container[datetime.date]) -> Decimal:
    return fines.outstanding_fees(db, member_id) + fines.accrued_late_fees(db, member_id, now, holidays)


def has_overdue_book_loan(db: Session, member_id: int, today: datetime.date) -> bool:
    stmt = sa.select(Loan.id).where(Loan.member_id == member_id, Loan.status == "open", Loan.due_date < today)
    return db.scalar(stmt.limit(1)) is not None


# --- lending -------------------------------------------------------------------------------


def _check_member(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    member: Member,
    equipment_type: EquipmentType,
) -> None:
    """Steps (4) to (11) of LIB-EQ-13."""
    today = now.date()
    if member.status == "passive":
        raise error("MEMBER_PASSIVE", "The member is passive")
    if today > member.valid_until:
        raise error("MEMBERSHIP_EXPIRED", "The membership has expired")
    if member.membership_type == "guest":
        raise error("EQUIPMENT_NOT_ALLOWED_FOR_TYPE", "Guests cannot borrow equipment")
    if overdue_open_loans(db, member.id, now) or has_overdue_book_loan(db, member.id, today):
        raise error("MEMBER_HAS_OVERDUE", "The member has an overdue loan")
    debt = total_debt(db, member.id, now, holidays)
    if debt >= DEBT_BLOCK:
        raise error("MEMBER_BLOCKED_BY_DEBT", "The member's debt blocks lending", total_debt=format_amount(debt))
    rules = EQUIPMENT_RULES[member.membership_type]
    if (
        equipment_type.requires_training
        and rules.training_needed
        and not has_valid_training(db, member.id, equipment_type.id, today)
    ):
        raise error("TRAINING_REQUIRED", "The member needs a valid training for this equipment type")
    if open_loans_of(db, member.id) >= rules.open_loans:
        raise error("EQUIPMENT_LIMIT_REACHED", "The member has reached the equipment loan limit", limit=rules.open_loans)
    if open_loans_of(db, member.id, equipment_type.id) >= equipment_type.max_open_per_member:
        raise error(
            "TYPE_LIMIT_REACHED",
            "The member has reached the loan limit of this equipment type",
            limit=equipment_type.max_open_per_member,
        )


def _check_desk(db: Session, now: datetime.datetime, holidays: Container[datetime.date], branch_id: int) -> None:
    """Steps (1) and (2) of LIB-EQ-13."""
    branch = db.get(Branch, branch_id)
    assert branch is not None
    if not branch.is_active:
        raise error("BRANCH_INACTIVE", f"Branch {branch.code} is inactive", field="branch_id", id=branch_id)
    if not desk_open(now, holidays):
        raise error(
            "DESK_CLOSED",
            "The equipment desk is closed",
            opens_at=format_datetime(next_desk_opening(now, holidays)),
        )


def lend(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    *,
    member_id: int,
    item_id: int | None,
    reservation_id: int | None,
) -> EquipmentLoan:
    """LIB-EQ-12, LIB-EQ-13, LIB-EQ-18, LIB-EQ-29."""
    member = db.get(Member, member_id)
    if member is None:
        raise reference_not_found("member_id", member_id)
    item: EquipmentItem | None = None
    reservation: EquipmentReservation | None = None
    if item_id is not None:
        item = db.get(EquipmentItem, item_id)
        if item is None:
            raise reference_not_found("item_id", item_id)
        type_id, branch_id = item.type_id, item.branch_id
    else:
        assert reservation_id is not None
        reservation = db.get(EquipmentReservation, reservation_id)
        if reservation is None:
            raise reference_not_found("reservation_id", reservation_id)
        type_id, branch_id = reservation.type_id, reservation.branch_id
    equipment_type = get_type_or_404(db, type_id)

    _check_desk(db, now, holidays, branch_id)
    if not equipment_type.is_active:
        raise error("TYPE_INACTIVE", "The equipment type is inactive")
    _check_member(db, now, holidays, member, equipment_type)

    due_at = due_at_from(now, equipment_type.period_unit, equipment_type.period, holidays)
    if reservation is not None:
        item = _check_collectable(db, now, member, reservation)  # LIB-EQ-29: no capacity check
    else:
        assert item is not None
        if item.status != "available":
            raise error("ITEM_NOT_AVAILABLE", "The item is not available", status=item.status)
        reservation = _own_reservation(db, now, member.id, item)  # LIB-EQ-18
        intervals = capacity.existing_intervals(
            db,
            item.type_id,
            item.branch_id,
            now,
            exclude_reservation_id=reservation.id if reservation is not None else None,
        )
        cap = capacity.capacity(db, item.type_id, item.branch_id)
        if not capacity.fits(intervals, (now, due_at + GRACE), cap, now):
            raise error("ITEM_NEEDED_FOR_RESERVATION", "A reservation needs the item", item_id=item.id)

    loan = EquipmentLoan(
        item_id=item.id,
        member_id=member.id,
        type_id=item.type_id,
        branch_id=item.branch_id,
        reservation_id=reservation.id if reservation is not None else None,
        loaned_at=now,
        due_at=due_at,
        extended=False,
        status="open",
        lent_by=actor.id,
        hourly_late_fee=equipment_type.hourly_late_fee,
    )
    db.add(loan)
    item.status = "on_loan"
    db.flush()
    if reservation is not None:
        reservation.status = "collected"
        reservation.loan_id = loan.id
        reservation.closed_at = now
    record(
        db,
        at=now,
        event="equipment_loan_created",
        actor_user_id=actor.id,
        entity_type="equipment_loan",
        entity_id=loan.id,
        details={
            "member_id": member.id,
            "item_id": item.id,
            "type_id": item.type_id,
            "branch_id": item.branch_id,
            "reservation_id": loan.reservation_id,
            "due_at": format_datetime(due_at),
        },
    )
    notify_equipment(
        db,
        now,
        member.id,
        "equipment_loan_created",
        f"You borrowed {equipment_type.name} ({item.asset_tag}). It is due at {format_datetime(due_at)}.",
        equipment_loan_id=loan.id,
    )
    return loan


def _own_reservation(db: Session, now: datetime.datetime, member_id: int, item: EquipmentItem) -> EquipmentReservation | None:
    """LIB-EQ-18: a ``booked`` reservation of the member for this type and branch that can be collected now."""
    stmt = (
        sa.select(EquipmentReservation)
        .where(
            EquipmentReservation.member_id == member_id,
            EquipmentReservation.type_id == item.type_id,
            EquipmentReservation.branch_id == item.branch_id,
            EquipmentReservation.status == "booked",
        )
        .order_by(EquipmentReservation.starts_at, EquipmentReservation.id)
    )
    for reservation in db.scalars(stmt):
        if reservation.starts_at - HOLD_EARLY <= now <= reservation.starts_at + COLLECT_LATE:
            return reservation
    return None


def _check_collectable(
    db: Session, now: datetime.datetime, member: Member, reservation: EquipmentReservation
) -> EquipmentItem:
    """LIB-EQ-29: the item that collects the reservation."""
    if reservation.member_id != member.id:
        raise error("RESERVATION_OF_OTHER_MEMBER", "The reservation belongs to another member")
    if reservation.status != "booked":
        raise error("RESERVATION_NOT_ACTIVE", "The reservation is not booked", status=reservation.status)
    if now < reservation.starts_at - HOLD_EARLY:
        raise error(
            "RESERVATION_NOT_READY",
            "The reservation cannot be collected yet",
            earliest=format_datetime(reservation.starts_at - HOLD_EARLY),
        )
    if now > reservation.starts_at + COLLECT_LATE:
        raise error("RESERVATION_EXPIRED", "The reservation has expired")
    stmt = (
        sa.select(EquipmentItem)
        .where(
            EquipmentItem.type_id == reservation.type_id,
            EquipmentItem.branch_id == reservation.branch_id,
            EquipmentItem.status == "available",
        )
        .order_by(EquipmentItem.asset_tag)
        .limit(1)
    )
    item = db.scalar(stmt)
    if item is None:
        raise error("ITEM_NOT_AVAILABLE", "No item of the type is available at the branch")
    return item


# --- extension -----------------------------------------------------------------------------


def extend(db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date], loan: EquipmentLoan) -> EquipmentLoan:
    """LIB-EQ-19."""
    if loan.status != "open":
        raise error("LOAN_NOT_OPEN", "The loan is not open", status=loan.status)
    if loan.extended:
        raise error("EXTENSION_LIMIT_REACHED", "The loan was already extended")
    if is_overdue(loan.due_at, now):
        raise error("LOAN_OVERDUE", "The loan is overdue", due_at=format_datetime(loan.due_at))
    equipment_type = get_type_or_404(db, loan.type_id)
    new_due = due_at_from(loan.due_at, equipment_type.period_unit, equipment_type.period, holidays)
    if equipment_type.period_unit == "hours" and new_due <= loan.due_at:
        raise error("EXTENSION_NOT_POSSIBLE", "The due time cannot be moved further", due_at=format_datetime(loan.due_at))
    intervals = capacity.existing_intervals(db, loan.type_id, loan.branch_id, now, exclude_loan_id=loan.id)
    cap = capacity.capacity(db, loan.type_id, loan.branch_id)
    if not capacity.fits(intervals, (loan.loaned_at, new_due + GRACE), cap, now):
        raise error("ITEM_NEEDED_FOR_RESERVATION", "A reservation needs the item", item_id=loan.item_id)
    old_due = loan.due_at
    loan.due_at = new_due
    loan.extended = True
    record(
        db,
        at=now,
        event="equipment_loan_extended",
        actor_user_id=actor.id,
        entity_type="equipment_loan",
        entity_id=loan.id,
        details={"member_id": loan.member_id, "due_at": {"old": format_datetime(old_due), "new": format_datetime(new_due)}},
    )
    return loan


# --- return and loss -----------------------------------------------------------------------


def _create_fee(
    db: Session, now: datetime.datetime, actor: User, loan: EquipmentLoan, kind: str, amount: Decimal
) -> None:
    fines.create_fee(
        db, now, actor, member_id=loan.member_id, loan_id=None, kind=kind, amount=amount, equipment_loan_id=loan.id
    )


def return_loan(
    db: Session,
    now: datetime.datetime,
    actor: User,
    loan: EquipmentLoan,
    *,
    condition: str,
    damage_fee: Decimal | None,
) -> EquipmentLoan:
    """LIB-EQ-20 to LIB-EQ-23, LIB-EQ-25."""
    if loan.status != "open":
        raise error("LOAN_NOT_OPEN", "The loan is not open", status=loan.status)
    item = db.get(EquipmentItem, loan.item_id)
    equipment_type = get_type_or_404(db, loan.type_id)
    assert item is not None
    if condition == "damaged":
        assert damage_fee is not None
        if damage_fee > item.value:
            raise error(
                "DAMAGE_FEE_EXCEEDS_VALUE",
                "The damage fee exceeds the value of the item",
                value=format_amount(item.value),
            )
    late_hours = late_hours_between(loan.due_at, now)
    loan.status = "returned"
    loan.returned_at = now
    loan.closed_at = now
    loan.received_by = actor.id
    loan.return_condition = condition
    loan.late_hours = late_hours
    if late_hours > 0:
        _create_fee(db, now, actor, loan, "equipment_late_fee", late_fee_amount(late_hours, loan.hourly_late_fee, item.value))
    if condition == "damaged":
        assert damage_fee is not None
        if damage_fee > ZERO:
            _create_fee(db, now, actor, loan, "equipment_damage_fee", damage_fee)
        item.status = "in_repair"
    else:
        item.status = "available"
    record(
        db,
        at=now,
        event="equipment_loan_returned",
        actor_user_id=actor.id,
        entity_type="equipment_loan",
        entity_id=loan.id,
        details={
            "member_id": loan.member_id,
            "item_id": item.id,
            "condition": condition,
            "damage_fee": format_amount(damage_fee) if damage_fee is not None else None,
            "late_hours": late_hours,
        },
    )
    notify_equipment(
        db,
        now,
        loan.member_id,
        "equipment_loan_returned",
        f"You returned {equipment_type.name} ({item.asset_tag}) (due at {format_datetime(loan.due_at)}).",
        equipment_loan_id=loan.id,
    )
    return loan


def report_lost(db: Session, now: datetime.datetime, actor: User, loan: EquipmentLoan) -> EquipmentLoan:
    """LIB-EQ-24."""
    if loan.status != "open":
        raise error("LOAN_NOT_OPEN", "The loan is not open", status=loan.status)
    item = db.get(EquipmentItem, loan.item_id)
    equipment_type = get_type_or_404(db, loan.type_id)
    assert item is not None
    late_hours = late_hours_between(loan.due_at, now)
    loan.status = "lost"
    loan.returned_at = None
    loan.closed_at = now
    loan.late_hours = late_hours
    if late_hours > 0:
        _create_fee(db, now, actor, loan, "equipment_late_fee", late_fee_amount(late_hours, loan.hourly_late_fee, item.value))
    _create_fee(db, now, actor, loan, "equipment_lost", item.value)
    item.status = "lost"
    record(
        db,
        at=now,
        event="equipment_loan_lost",
        actor_user_id=actor.id,
        entity_type="equipment_loan",
        entity_id=loan.id,
        details={"member_id": loan.member_id, "item_id": item.id, "late_hours": late_hours},
    )
    notify_equipment(
        db,
        now,
        loan.member_id,
        "equipment_loan_lost",
        f"Your loan of {equipment_type.name} ({item.asset_tag}) (due at {format_datetime(loan.due_at)}) "
        "was reported as lost.",
        equipment_loan_id=loan.id,
    )
    return loan


def accrued_for(db: Session, loan: EquipmentLoan, now: datetime.datetime) -> Decimal:
    return accrued_late_fee(db, loan, now)


def loan_list_stmt(
    now: datetime.datetime,
    *,
    member_id: int | None = None,
    status: str | None = None,
    type_id: int | None = None,
    branch_id: int | None = None,
    overdue: bool | None = None,
) -> sa.Select[tuple[EquipmentLoan]]:
    """LIB-EQ-17."""
    stmt = sa.select(EquipmentLoan).order_by(EquipmentLoan.loaned_at, EquipmentLoan.id)
    if member_id is not None:
        stmt = stmt.where(EquipmentLoan.member_id == member_id)
    if status is not None:
        stmt = stmt.where(EquipmentLoan.status == status)
    if type_id is not None:
        stmt = stmt.where(EquipmentLoan.type_id == type_id)
    if branch_id is not None:
        stmt = stmt.where(EquipmentLoan.branch_id == branch_id)
    if overdue is not None:
        is_late = sa.and_(EquipmentLoan.status == "open", EquipmentLoan.due_at < now - GRACE)
        stmt = stmt.where(is_late if overdue else sa.not_(is_late))
    return stmt
