"""Types, items and training (LIB-EQ-03 to LIB-EQ-11)."""

from __future__ import annotations

import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.service import require_active_branch
from lms.core.errors import Conflict, NotFound, ValidationFailed, reference_not_found
from lms.core.money import format_amount
from lms.core.text import normalize
from lms.core.timeutil import format_datetime
from lms.equipment import capacity
from lms.equipment.models import (
    EquipmentItem,
    EquipmentReservation,
    EquipmentTraining,
    EquipmentType,
)
from lms.equipment.rules import valid_training_until
from lms.equipment.schemas import type_range_problems
from lms.members.models import Member
from lms.notifications.service import notify_equipment


def get_type_or_404(db: Session, type_id: int) -> EquipmentType:
    equipment_type = db.get(EquipmentType, type_id)
    if equipment_type is None:
        raise NotFound(f"Equipment type {type_id} does not exist", details={"resource": "equipment_type", "id": type_id})
    return equipment_type


def get_item_or_404(db: Session, item_id: int) -> EquipmentItem:
    item = db.get(EquipmentItem, item_id)
    if item is None:
        raise NotFound(f"Equipment item {item_id} does not exist", details={"resource": "equipment_item", "id": item_id})
    return item


def type_or_reference_404(db: Session, field: str, type_id: int) -> EquipmentType:
    equipment_type = db.get(EquipmentType, type_id)
    if equipment_type is None:
        raise reference_not_found(field, type_id)
    return equipment_type


# --- types ---------------------------------------------------------------------------------


def item_counts(db: Session, type_id: int) -> tuple[int, int]:
    """``items_total`` (not retired) and ``items_available`` over all branches (LIB-EQ-06)."""
    total = db.scalar(
        sa.select(sa.func.count()).select_from(EquipmentItem).where(
            EquipmentItem.type_id == type_id, EquipmentItem.status != "retired"
        )
    )
    available = db.scalar(
        sa.select(sa.func.count()).select_from(EquipmentItem).where(
            EquipmentItem.type_id == type_id, EquipmentItem.status == "available"
        )
    )
    return total or 0, available or 0


def _type_snapshot(t: EquipmentType) -> dict[str, Any]:
    return {
        "name": t.name,
        "period": t.period,
        "hourly_late_fee": format_amount(t.hourly_late_fee),
        "requires_training": t.requires_training,
        "max_open_per_member": t.max_open_per_member,
        "is_active": t.is_active,
    }


def create_type(
    db: Session,
    now: datetime.datetime,
    actor: User,
    *,
    code: str,
    name: str,
    period_unit: str,
    period: int,
    hourly_late_fee: Any,
    requires_training: bool,
    max_open_per_member: int,
) -> EquipmentType:
    """LIB-EQ-03."""
    problems = type_range_problems(period_unit, period, hourly_late_fee, max_open_per_member)
    if problems:
        raise ValidationFailed(problems)
    if db.scalar(sa.select(EquipmentType.id).where(EquipmentType.code == code)) is not None:
        raise Conflict("An equipment type with this code already exists", details={"field": "code"})
    equipment_type = EquipmentType(
        code=code,
        name=name,
        period_unit=period_unit,
        period=period,
        hourly_late_fee=hourly_late_fee,
        requires_training=requires_training,
        max_open_per_member=max_open_per_member,
        is_active=True,
    )
    db.add(equipment_type)
    db.flush()
    record(
        db,
        at=now,
        event="equipment_type_created",
        actor_user_id=actor.id,
        entity_type="equipment_type",
        entity_id=equipment_type.id,
        details={"code": code, "period_unit": period_unit, **_type_snapshot(equipment_type)},
    )
    return equipment_type


def update_type(
    db: Session, now: datetime.datetime, actor: User, equipment_type: EquipmentType, fields: dict[str, Any]
) -> EquipmentType:
    """LIB-EQ-04, LIB-EQ-05. ``fields`` holds only the fields present in the request."""
    new = {name: fields.get(name, value) for name, value in _type_snapshot_raw(equipment_type).items()}
    problems = type_range_problems(
        equipment_type.period_unit, new["period"], new["hourly_late_fee"], new["max_open_per_member"]
    )
    if problems:
        raise ValidationFailed(problems)

    old = _type_snapshot(equipment_type)
    deactivating = equipment_type.is_active and new["is_active"] is False
    for name, value in new.items():
        setattr(equipment_type, name, value)
    diff = changes(old, _type_snapshot(equipment_type))
    if diff:
        record(
            db,
            at=now,
            event="equipment_type_updated",
            actor_user_id=actor.id,
            entity_type="equipment_type",
            entity_id=equipment_type.id,
            details=diff,
        )
    if deactivating:
        stmt = (
            sa.select(EquipmentReservation)
            .where(EquipmentReservation.type_id == equipment_type.id, EquipmentReservation.status == "booked")
            .order_by(EquipmentReservation.starts_at, EquipmentReservation.id)
        )
        for reservation in list(db.scalars(stmt)):
            cancel_reservation(db, now, actor.id, reservation, "type_inactive", equipment_type)
    return equipment_type


def _type_snapshot_raw(t: EquipmentType) -> dict[str, Any]:
    return {
        "name": t.name,
        "period": t.period,
        "hourly_late_fee": t.hourly_late_fee,
        "requires_training": t.requires_training,
        "max_open_per_member": t.max_open_per_member,
        "is_active": t.is_active,
    }


def cancel_reservation(
    db: Session,
    now: datetime.datetime,
    actor_id: int | None,
    reservation: EquipmentReservation,
    reason: str,
    equipment_type: EquipmentType | None = None,
) -> None:
    """Cancel a ``booked`` reservation (LIB-EQ-05, LIB-EQ-30, LIB-EQ-35); reasons other than ``member_request`` notify."""
    equipment_type = equipment_type or get_type_or_404(db, reservation.type_id)
    reservation.status = "cancelled"
    reservation.closed_at = now
    reservation.cancel_reason = reason
    record(
        db,
        at=now,
        event="equipment_reservation_cancelled",
        actor_user_id=actor_id,
        entity_type="equipment_reservation",
        entity_id=reservation.id,
        details={"reason": reason, "type_id": reservation.type_id, "member_id": reservation.member_id},
    )
    if reason != "member_request":
        message = (
            f"Your reservation of {equipment_type.name} for {format_datetime(reservation.starts_at)} "
            f"was cancelled ({reason})."
        )
        notify_equipment(
            db,
            now,
            reservation.member_id,
            "equipment_reservation_cancelled",
            message,
            equipment_reservation_id=reservation.id,
        )


# --- items ---------------------------------------------------------------------------------


def create_item(
    db: Session,
    now: datetime.datetime,
    actor: User,
    *,
    type_id: int,
    asset_tag: str,
    serial_no: str,
    branch_id: int,
    value: Any,
    acquired_on: datetime.date,
) -> EquipmentItem:
    """LIB-EQ-07."""
    if acquired_on > now.date():
        raise ValidationFailed.single("acquired_on", "acquired_on must not be after today")
    type_or_reference_404(db, "type_id", type_id)
    require_active_branch(db, "branch_id", branch_id)
    if db.scalar(sa.select(EquipmentItem.id).where(EquipmentItem.asset_tag == asset_tag)) is not None:
        raise Conflict("An equipment item with this asset tag already exists", details={"field": "asset_tag"})
    item = EquipmentItem(
        type_id=type_id,
        asset_tag=asset_tag,
        serial_no=serial_no,
        branch_id=branch_id,
        value=value,
        status="available",
        acquired_on=acquired_on,
        created_at=now,
    )
    db.add(item)
    db.flush()
    record(
        db,
        at=now,
        event="equipment_item_created",
        actor_user_id=actor.id,
        entity_type="equipment_item",
        entity_id=item.id,
        details={
            "type_id": type_id,
            "asset_tag": asset_tag,
            "serial_no": serial_no,
            "branch_id": branch_id,
            "value": format_amount(value),
            "acquired_on": acquired_on.isoformat(),
        },
    )
    return item


def _item_error(code: str, message: str, item: EquipmentItem) -> Conflict:
    return Conflict(message, code=code, details={"id": item.id, "status": item.status})


def update_item(db: Session, now: datetime.datetime, actor: User, item: EquipmentItem, fields: dict[str, Any]) -> EquipmentItem:
    """LIB-EQ-08."""
    moving = "branch_id" in fields and fields["branch_id"] != item.branch_id
    if "branch_id" in fields:
        require_active_branch(db, "branch_id", fields["branch_id"])
    if moving:
        if item.status != "available":
            raise _item_error("INVALID_ITEM_STATUS", "The branch of an item can only change while it is available", item)
        if not capacity.survives_removal_of_item(db, item, now):
            raise _item_error("ITEM_NEEDED_FOR_RESERVATION", "A reservation needs this item at its branch", item)
    names = ("serial_no", "value", "branch_id")
    old = {n: getattr(item, n) for n in names}
    for name in names:
        if name in fields:
            setattr(item, name, fields[name])
    diff = changes(
        {n: format_amount(v) if n == "value" else v for n, v in old.items()},
        {n: format_amount(getattr(item, n)) if n == "value" else getattr(item, n) for n in names},
    )
    if diff:
        record(
            db,
            at=now,
            event="equipment_item_updated",
            actor_user_id=actor.id,
            entity_type="equipment_item",
            entity_id=item.id,
            details=diff,
        )
    return item


def retire_item(db: Session, now: datetime.datetime, actor: User, item: EquipmentItem) -> EquipmentItem:
    """LIB-EQ-10."""
    if item.status not in ("available", "in_repair"):
        raise _item_error("INVALID_ITEM_STATUS", "Only an available or in_repair item can be retired", item)
    if not capacity.survives_removal_of_item(db, item, now):
        raise _item_error("ITEM_NEEDED_FOR_RESERVATION", "A reservation needs this item", item)
    old = item.status
    item.status = "retired"
    record(
        db,
        at=now,
        event="equipment_item_retired",
        actor_user_id=actor.id,
        entity_type="equipment_item",
        entity_id=item.id,
        details={"status": {"old": old, "new": "retired"}},
    )
    return item


def repair_done(db: Session, now: datetime.datetime, actor: User, item: EquipmentItem) -> EquipmentItem:
    """LIB-EQ-10."""
    if item.status != "in_repair":
        raise _item_error("INVALID_ITEM_STATUS", "Only an in_repair item can come back from repair", item)
    item.status = "available"
    record(
        db,
        at=now,
        event="equipment_item_repaired",
        actor_user_id=actor.id,
        entity_type="equipment_item",
        entity_id=item.id,
        details={"status": {"old": "in_repair", "new": "available"}},
    )
    return item


def item_list_stmt(
    *, type_id: int | None, branch_id: int | None, status: str | None, q: str | None
) -> sa.Select[tuple[EquipmentItem]]:
    """LIB-EQ-09."""
    stmt = sa.select(EquipmentItem).order_by(EquipmentItem.asset_tag, EquipmentItem.id)
    if type_id is not None:
        stmt = stmt.where(EquipmentItem.type_id == type_id)
    if branch_id is not None:
        stmt = stmt.where(EquipmentItem.branch_id == branch_id)
    if status is not None:
        stmt = stmt.where(EquipmentItem.status == status)
    if q is not None and q.strip():
        needle = normalize(q.strip())
        stmt = stmt.where(
            sa.or_(
                sa.func.lms_normalize(EquipmentItem.asset_tag).contains(needle, autoescape=True),
                sa.func.lms_normalize(EquipmentItem.serial_no).contains(needle, autoescape=True),
            )
        )
    return stmt


# --- training ------------------------------------------------------------------------------


def has_valid_training(db: Session, member_id: int, type_id: int, day: datetime.date) -> bool:
    """LIB-EQ-11."""
    stmt = sa.select(EquipmentTraining.id).where(
        EquipmentTraining.member_id == member_id,
        EquipmentTraining.type_id == type_id,
        EquipmentTraining.completed_on <= day,
        EquipmentTraining.valid_until >= day,
    )
    return db.scalar(stmt.limit(1)) is not None


def record_training(
    db: Session,
    now: datetime.datetime,
    actor: User,
    member: Member,
    *,
    type_id: int,
    completed_on: datetime.date,
) -> EquipmentTraining:
    """LIB-EQ-11."""
    if completed_on > now.date():
        raise ValidationFailed.single("completed_on", "completed_on must not be after today")
    equipment_type = type_or_reference_404(db, "type_id", type_id)
    if not equipment_type.requires_training:
        raise Conflict("The equipment type does not require training", code="TRAINING_NOT_REQUIRED", details={"type_id": type_id})
    training = EquipmentTraining(
        member_id=member.id,
        type_id=type_id,
        completed_on=completed_on,
        valid_until=valid_training_until(completed_on),
        recorded_by=actor.id,
        created_at=now,
    )
    db.add(training)
    db.flush()
    record(
        db,
        at=now,
        event="equipment_training_recorded",
        actor_user_id=actor.id,
        entity_type="equipment_training",
        entity_id=training.id,
        details={
            "member_id": member.id,
            "type_id": type_id,
            "completed_on": completed_on.isoformat(),
            "valid_until": training.valid_until.isoformat(),
        },
    )
    return training
