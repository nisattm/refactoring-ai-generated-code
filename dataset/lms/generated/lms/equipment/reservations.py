"""Reservations, expiry, overdue notices and availability (LIB-EQ-26 to LIB-EQ-34)."""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.calendar import is_working_day
from lms.core.clock import LOCAL_TZ
from lms.core.errors import NotFound, reference_not_found
from lms.core.money import format_amount
from lms.core.timeutil import format_datetime
from lms.equipment import capacity
from lms.equipment.inventory import cancel_reservation, get_type_or_404, has_valid_training
from lms.equipment.lending import error, total_debt
from lms.equipment.models import EquipmentItem, EquipmentLoan, EquipmentReservation, EquipmentType
from lms.equipment.rules import (
    DEBT_BLOCK,
    DESK_CLOSES,
    DESK_OPENS,
    EQUIPMENT_RULES,
    GRACE,
    HALF_HOUR,
    MAX_AHEAD_DAYS,
    MIN_LEAD,
    at_local,
    desk_open,
    due_at_from,
    next_desk_opening,
)
from lms.equipment.schemas import AvailabilityOut, SlotOut
from lms.members.models import Member
from lms.notifications.service import equipment_overdue_notice_sent, notify_equipment


def get_reservation_or_404(db: Session, reservation_id: int) -> EquipmentReservation:
    reservation = db.get(EquipmentReservation, reservation_id)
    if reservation is None:
        raise NotFound(
            f"Equipment reservation {reservation_id} does not exist",
            details={"resource": "equipment_reservation", "id": reservation_id},
        )
    return reservation


def booked_count(db: Session, member_id: int) -> int:
    stmt = sa.select(sa.func.count()).select_from(EquipmentReservation).where(
        EquipmentReservation.member_id == member_id, EquipmentReservation.status == "booked"
    )
    return db.scalar(stmt) or 0


def _booked_overlapping(
    db: Session, member_id: int, type_id: int, starts_at: datetime.datetime, ends_at: datetime.datetime
) -> bool:
    stmt = sa.select(EquipmentReservation).where(
        EquipmentReservation.member_id == member_id,
        EquipmentReservation.type_id == type_id,
        EquipmentReservation.status == "booked",
    )
    return any(r.starts_at < ends_at and starts_at < r.ends_at for r in db.scalars(stmt))


def _next_free_at(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    equipment_type: EquipmentType,
    branch_id: int,
    after: datetime.datetime,
) -> datetime.datetime | None:
    """LIB-EQ-28 (13): the earliest later start at which the capacity rule holds."""
    last_day = now.date() + datetime.timedelta(days=MAX_AHEAD_DAYS)
    intervals = capacity.existing_intervals(db, equipment_type.id, branch_id, now)
    cap = capacity.capacity(db, equipment_type.id, branch_id)
    candidate = after + HALF_HOUR
    while candidate.date() <= last_day:
        if desk_open(candidate, holidays):
            ends_at = due_at_from(candidate, equipment_type.period_unit, equipment_type.period, holidays)
            if capacity.fits(intervals, capacity.hold_interval(candidate, ends_at), cap, now):
                return candidate
        candidate += HALF_HOUR
    return None


def create_reservation(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    *,
    type_id: int,
    branch_id: int,
    member_id: int,
    starts_at: datetime.datetime,
) -> EquipmentReservation:
    """LIB-EQ-26, LIB-EQ-28."""
    equipment_type = db.get(EquipmentType, type_id)
    if equipment_type is None:
        raise reference_not_found("type_id", type_id)
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise reference_not_found("branch_id", branch_id)
    member = db.get(Member, member_id)
    if member is None:
        raise reference_not_found("member_id", member_id)

    today = now.date()
    ends_at = due_at_from(starts_at, equipment_type.period_unit, equipment_type.period, holidays)
    rules = EQUIPMENT_RULES[member.membership_type]
    if not branch.is_active:
        raise error("BRANCH_INACTIVE", f"Branch {branch.code} is inactive", field="branch_id", id=branch_id)
    if not equipment_type.is_active:
        raise error("TYPE_INACTIVE", "The equipment type is inactive")
    if member.status == "passive":
        raise error("MEMBER_PASSIVE", "The member is passive")
    if ends_at.date() > member.valid_until:
        raise error("MEMBERSHIP_EXPIRED", "The membership is not valid at the end of the reservation")
    if member.membership_type == "guest":
        raise error("EQUIPMENT_NOT_ALLOWED_FOR_TYPE", "Guests cannot reserve equipment")
    debt = total_debt(db, member.id, now, holidays)
    if debt >= DEBT_BLOCK:
        raise error("MEMBER_BLOCKED_BY_DEBT", "The member's debt blocks reservations", total_debt=format_amount(debt))
    if (
        equipment_type.requires_training
        and rules.training_needed
        and not has_valid_training(db, member.id, equipment_type.id, starts_at.date())
    ):
        raise error("TRAINING_REQUIRED", "The member needs a valid training for this equipment type")
    if not desk_open(starts_at, holidays):
        raise error(
            "DESK_CLOSED", "The equipment desk is closed at the start", opens_at=format_datetime(next_desk_opening(starts_at, holidays))
        )
    if starts_at < now + MIN_LEAD:
        raise error("RESERVATION_TOO_SOON", "A reservation must start at least 30 minutes from now")
    latest = today + datetime.timedelta(days=MAX_AHEAD_DAYS)
    if starts_at.date() > latest:
        raise error("RESERVATION_TOO_FAR_AHEAD", "The reservation is too far ahead", latest_date=latest.isoformat())
    if booked_count(db, member.id) >= rules.reservations:
        raise error(
            "EQUIPMENT_RESERVATION_LIMIT_REACHED", "The member has reached the reservation limit", limit=rules.reservations
        )
    if _booked_overlapping(db, member.id, type_id, starts_at, ends_at):
        raise error("DUPLICATE_EQUIPMENT_RESERVATION", "The member already has an overlapping reservation of this type")
    intervals = capacity.existing_intervals(db, type_id, branch_id, now)
    cap = capacity.capacity(db, type_id, branch_id)
    if not capacity.fits(intervals, capacity.hold_interval(starts_at, ends_at), cap, now):
        next_free = _next_free_at(db, now, holidays, equipment_type, branch_id, starts_at)
        raise error(
            "NO_EQUIPMENT_AVAILABLE",
            "No equipment of this type is available at that time",
            next_free_at=format_datetime(next_free) if next_free is not None else None,
        )

    reservation = EquipmentReservation(
        type_id=type_id,
        branch_id=branch_id,
        member_id=member.id,
        starts_at=starts_at,
        ends_at=ends_at,
        status="booked",
        created_at=now,
    )
    db.add(reservation)
    db.flush()
    record(
        db,
        at=now,
        event="equipment_reservation_created",
        actor_user_id=actor.id,
        entity_type="equipment_reservation",
        entity_id=reservation.id,
        details={
            "member_id": member.id,
            "type_id": type_id,
            "branch_id": branch_id,
            "starts_at": format_datetime(starts_at),
            "ends_at": format_datetime(ends_at),
        },
    )
    return reservation


def cancel(
    db: Session, now: datetime.datetime, actor: User, reservation: EquipmentReservation, *, by_member: bool
) -> EquipmentReservation:
    """LIB-EQ-30."""
    if reservation.status != "booked":
        raise error("RESERVATION_NOT_ACTIVE", "The reservation is not booked", status=reservation.status)
    cancel_reservation(db, now, actor.id, reservation, "member_request" if by_member else "staff_request")
    return reservation


def cancel_for_deactivation(db: Session, now: datetime.datetime, actor_id: int | None, member_id: int) -> None:
    """LIB-EQ-35."""
    stmt = (
        sa.select(EquipmentReservation)
        .where(EquipmentReservation.member_id == member_id, EquipmentReservation.status == "booked")
        .order_by(EquipmentReservation.starts_at, EquipmentReservation.id)
    )
    for reservation in list(db.scalars(stmt)):
        cancel_reservation(db, now, actor_id, reservation, "member_deactivated")


# --- processing ----------------------------------------------------------------------------


def process(db: Session, now: datetime.datetime, actor: User) -> tuple[int, int]:
    """LIB-EQ-31, LIB-EQ-32."""
    stmt = (
        sa.select(EquipmentReservation)
        .where(EquipmentReservation.status == "booked")
        .order_by(EquipmentReservation.starts_at, EquipmentReservation.id)
    )
    expired = 0
    for reservation in list(db.scalars(stmt)):
        if not capacity.is_expired(reservation, now):
            continue
        equipment_type = get_type_or_404(db, reservation.type_id)
        reservation.status = "expired"
        reservation.closed_at = now
        record(
            db,
            at=now,
            event="equipment_reservation_expired",
            actor_user_id=actor.id,
            entity_type="equipment_reservation",
            entity_id=reservation.id,
            details={"member_id": reservation.member_id, "type_id": reservation.type_id},
        )
        notify_equipment(
            db,
            now,
            reservation.member_id,
            "equipment_reservation_expired",
            f"Your reservation of {equipment_type.name} for {format_datetime(reservation.starts_at)} "
            "expired because it was not collected.",
            equipment_reservation_id=reservation.id,
        )
        expired += 1

    notices = 0
    today = now.date()
    overdue = db.scalars(
        sa.select(EquipmentLoan)
        .where(EquipmentLoan.status == "open", EquipmentLoan.due_at < now - GRACE)
        .order_by(EquipmentLoan.id)
    )
    for loan in list(overdue):
        if equipment_overdue_notice_sent(db, loan.id, today):
            continue
        equipment_type = get_type_or_404(db, loan.type_id)
        item = db.get(EquipmentItem, loan.item_id)
        assert item is not None
        notify_equipment(
            db,
            now,
            loan.member_id,
            "equipment_overdue",
            f"Your loan of {equipment_type.name} ({item.asset_tag}) was due at {format_datetime(loan.due_at)} "
            "and is overdue.",
            equipment_loan_id=loan.id,
            reminder_date=today,
        )
        notices += 1

    record(
        db,
        at=now,
        event="equipment_processed",
        actor_user_id=actor.id,
        entity_type="equipment",
        entity_id=None,
        details={"expired_reservations": expired, "overdue_notices": notices},
    )
    return expired, notices


# --- availability --------------------------------------------------------------------------


def availability(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    equipment_type: EquipmentType,
    branch_id: int,
    day: datetime.date,
) -> AvailabilityOut:
    """LIB-EQ-33."""
    cap = capacity.capacity(db, equipment_type.id, branch_id)
    slots: list[SlotOut] = []
    if is_working_day(day, holidays):
        intervals = capacity.existing_intervals(db, equipment_type.id, branch_id, now)
        cursor = at_local(day, DESK_OPENS)
        close = at_local(day, DESK_CLOSES)
        while cursor < close:
            peak = capacity.max_demand(intervals, cursor, cursor + HALF_HOUR)
            slots.append(SlotOut(start=cursor.strftime("%H:%M"), free=max(cap - peak, 0)))
            cursor += HALF_HOUR
    return AvailabilityOut(
        type_id=equipment_type.id, branch_id=branch_id, date=day.isoformat(), capacity=cap, slots=slots
    )


def reservation_list_stmt(
    *,
    member_id: int | None = None,
    status: str | None = None,
    type_id: int | None = None,
    branch_id: int | None = None,
    first: datetime.date | None = None,
    last: datetime.date | None = None,
) -> sa.Select[tuple[EquipmentReservation]]:
    """LIB-EQ-34. ``first`` and ``last`` are inclusive local dates of ``starts_at``."""
    stmt = sa.select(EquipmentReservation).order_by(EquipmentReservation.starts_at, EquipmentReservation.id)
    if member_id is not None:
        stmt = stmt.where(EquipmentReservation.member_id == member_id)
    if status is not None:
        stmt = stmt.where(EquipmentReservation.status == status)
    if type_id is not None:
        stmt = stmt.where(EquipmentReservation.type_id == type_id)
    if branch_id is not None:
        stmt = stmt.where(EquipmentReservation.branch_id == branch_id)
    if first is not None:
        stmt = stmt.where(EquipmentReservation.starts_at >= datetime.datetime.combine(first, datetime.time.min, LOCAL_TZ))
    if last is not None:
        end = datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time.min, LOCAL_TZ)
        stmt = stmt.where(EquipmentReservation.starts_at < end)
    return stmt
