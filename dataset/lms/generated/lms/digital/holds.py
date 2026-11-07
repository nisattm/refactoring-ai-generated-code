"""Holds (LIB-DIG-22 to LIB-DIG-27)."""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.auth.models import User
from lms.core.errors import NotFound
from lms.digital import state
from lms.digital.models import DigitalHold, DigitalLoan, DigitalResource
from lms.digital.queue import cancel_hold, move_queue
from lms.digital.rules import DIGITAL_RULES
from lms.members.models import Member


def get_hold_or_404(db: Session, hold_id: int) -> DigitalHold:
    hold = db.get(DigitalHold, hold_id)
    if hold is None:
        raise NotFound(f"Digital hold {hold_id} does not exist", details={"resource": "digital_hold", "id": hold_id})
    return hold


def place_hold(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    resource: DigitalResource,
    member: Member,
) -> DigitalHold:
    """LIB-DIG-22, LIB-DIG-23."""
    if resource.kind != "ebook":
        raise state.error("WRONG_RESOURCE_KIND", "The resource is a database, not an e-book", kind=resource.kind)
    state.check_member_and_resource(db, now, holidays, resource, member)
    already = db.scalar(
        sa.select(DigitalLoan.id)
        .where(
            DigitalLoan.member_id == member.id,
            DigitalLoan.resource_id == resource.id,
            DigitalLoan.status == "open",
            DigitalLoan.due_at > now,
        )
        .limit(1)
    )
    if already is not None:
        raise state.error("ALREADY_BORROWED", "The member has already borrowed this e-book", loan_id=already)
    if state.current_hold(db, member.id, resource.id, now) is not None:
        raise state.error("DUPLICATE_HOLD", "The member already has a hold on this e-book")
    limit = DIGITAL_RULES[member.membership_type].holds
    if state.member_holds(db, member.id, now) >= limit:
        raise state.error("DIGITAL_HOLD_LIMIT_REACHED", "The member has reached the hold limit", limit=limit)
    if state.capacity_at(db, resource.id, now) == 0:
        raise state.error("NO_ACTIVE_LICENSE", "The resource has no active license")
    if state.free_copies(db, resource.id, now) > 0:
        raise state.error("HOLD_NOT_NEEDED", "A copy is available: borrow it now")
    hold = DigitalHold(resource_id=resource.id, member_id=member.id, status="waiting", created_at=now)
    db.add(hold)
    db.flush()
    state.audit(
        db, now, actor.id, "digital_hold_created", "digital_hold", hold.id, resource_id=resource.id, member_id=member.id
    )
    return hold


def cancel(db: Session, now: datetime.datetime, actor: User, hold: DigitalHold, *, by_member: bool) -> DigitalHold:
    """LIB-DIG-25."""
    if hold.status not in ("waiting", "ready") or hold.is_lapsed(now):
        raise state.error("HOLD_NOT_ACTIVE", "The hold is not active", status=hold.status)
    was_ready = hold.status == "ready"
    cancel_hold(db, now, actor.id, hold, "member_request" if by_member else "staff_request")
    if was_ready:
        resource = state.get_resource_or_404(db, hold.resource_id)
        move_queue(db, now, actor.id, resource)
    return hold


def resource_hold_stmt(resource_id: int, status: str) -> sa.Select[tuple[DigitalHold]]:
    """LIB-DIG-24."""
    return (
        sa.select(DigitalHold)
        .where(DigitalHold.resource_id == resource_id, DigitalHold.status == status)
        .order_by(DigitalHold.created_at, DigitalHold.id)
    )


def member_hold_stmt(member_id: int, status: str | None) -> sa.Select[tuple[DigitalHold]]:
    stmt = sa.select(DigitalHold).where(DigitalHold.member_id == member_id).order_by(DigitalHold.created_at, DigitalHold.id)
    if status is not None:
        stmt = stmt.where(DigitalHold.status == status)
    return stmt
