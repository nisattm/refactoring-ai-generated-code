"""Holds: cancelling and moving the queue (LIB-DIG-25, LIB-DIG-26)."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.core.timeutil import format_datetime
from lms.digital import state
from lms.digital.models import DigitalHold, DigitalResource
from lms.digital.rules import HOLD_KEEP
from lms.notifications.service import notify_digital


def cancel_hold(
    db: Session, now: datetime.datetime, actor_id: int | None, hold: DigitalHold, reason: str
) -> DigitalHold:
    """Set a ``waiting`` or ``ready`` hold to ``cancelled``; the member is told unless they asked for it."""
    hold.status = "cancelled"
    hold.closed_at = now
    hold.cancel_reason = reason
    state.audit(
        db,
        now,
        actor_id,
        "digital_hold_cancelled",
        "digital_hold",
        hold.id,
        resource_id=hold.resource_id,
        member_id=hold.member_id,
        reason=reason,
    )
    if reason != "member_request":
        resource = db.get(DigitalResource, hold.resource_id)
        assert resource is not None
        notify_digital(
            db,
            now,
            hold.member_id,
            "digital_hold_cancelled",
            f'Your hold on "{resource.title}" was cancelled ({reason}).',
            digital_hold_id=hold.id,
        )
    return hold


def move_queue(db: Session, now: datetime.datetime, actor_id: int | None, resource: DigitalResource) -> int:
    """LIB-DIG-26: returns the number of holds that became ``ready``."""
    if not resource.is_active or resource.kind != "ebook":
        return 0
    capacity = state.capacity_at(db, resource.id, now)
    active = state.active_loan_count(db, resource.id, now)
    moved = 0
    while True:
        kept = state.kept_copy_count(db, resource.id, now)
        if capacity - active - kept <= 0:
            break
        hold = db.scalars(
            sa.select(DigitalHold)
            .where(DigitalHold.resource_id == resource.id, DigitalHold.status == "waiting")
            .order_by(DigitalHold.created_at, DigitalHold.id)
        ).first()
        if hold is None:
            break
        hold.status = "ready"
        hold.ready_at = now
        hold.ready_until = now + HOLD_KEEP
        db.flush()
        state.audit(
            db,
            now,
            actor_id,
            "digital_hold_ready",
            "digital_hold",
            hold.id,
            resource_id=resource.id,
            member_id=hold.member_id,
            ready_until=format_datetime(hold.ready_until),
        )
        notify_digital(
            db,
            now,
            hold.member_id,
            "digital_hold_ready",
            f'Your hold on "{resource.title}" is ready. Borrow it by {format_datetime(hold.ready_until)}.',
            digital_hold_id=hold.id,
        )
        moved += 1
    return moved
