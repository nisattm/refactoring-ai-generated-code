"""Missing and found copies, processing (LIB-INV-20 to LIB-INV-24, LIB-INV-26, LIB-INV-28)."""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.service import require_active_branch
from lms.catalog.models import Copy
from lms.reservations.service import release_copy
from lms.catalog.status import invalid_status, set_status
from lms.courses.models import ReadingListItem
from lms.courses.reserve import refresh_item_status
from lms.inventory import rules
from lms.inventory.models import InventoryCount
from lms.notifications.service import notify_reservation
from lms.reservations.models import Reservation


def mark_missing(db: Session, now: datetime.datetime, copy: Copy) -> None:
    """LIB-INV-18 step 1: a copy with a shelf status becomes ``missing``."""
    was = copy.status
    set_status(copy, "missing")
    copy.missing_since = now.date()
    db.flush()
    if was == "on_hold":  # LIB-INV-20
        reservation = db.scalar(
            sa.select(Reservation).where(Reservation.copy_id == copy.id, Reservation.status == "ready")
        )
        if reservation is not None:
            reservation.status = "waiting"
            reservation.copy_id = None
            reservation.ready_on = None
            reservation.hold_until = None
            db.flush()
            notify_reservation(db, now, "reservation_delayed", reservation)
    elif was == "on_reserve":  # LIB-INV-21
        item_id = copy.reserve_item_id
        copy.reserve_item_id = None
        copy.reserve_course_id = None
        db.flush()
        item = db.get(ReadingListItem, item_id) if item_id is not None else None
        if item is not None:
            refresh_item_status(db, item)


def restore_copy(
    db: Session,
    now: datetime.datetime,
    actor_user_id: int | None,
    holidays: Container[datetime.date],
    copy: Copy,
    branch_id: int,
) -> None:
    """The effects of LIB-INV-18 step 2 and LIB-INV-22: a ``missing`` or ``lost`` copy is at ``branch_id``
    again and is released (LIB-RES-08)."""
    copy.status = "available"  # from ``lost`` as well as from ``missing``; the release procedure decides on
    copy.current_branch_id = branch_id
    copy.missing_since = None
    db.flush()
    release_copy(db, copy, now, holidays, actor_user_id)


def found_copy(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    copy: Copy,
    branch_id: int,
) -> Copy:
    """LIB-INV-22."""
    require_active_branch(db, "branch_id", branch_id)
    if copy.status not in ("missing", "lost"):
        raise invalid_status(copy, "marking as found")
    previous = copy.status
    restore_copy(db, now, actor.id, holidays, copy, branch_id)
    record(
        db,
        at=now,
        event="copy_found",
        actor_user_id=actor.id,
        entity_type="copy",
        entity_id=copy.id,
        details={"branch_id": branch_id, "previous_status": previous},
    )
    return copy


def process(db: Session, now: datetime.datetime, actor: User) -> tuple[int, int]:
    """LIB-INV-23: ``(expired_counts, marked_lost)``."""
    limit = now - datetime.timedelta(days=rules.COUNT_EXPIRY_DAYS)
    stale = db.scalars(
        sa.select(InventoryCount)
        .where(InventoryCount.status == "open", InventoryCount.started_at < limit)
        .order_by(InventoryCount.id)
    ).all()
    for count in stale:
        count.status = "cancelled"
        count.cancel_reason = "expired"
    cutoff = now.date() - datetime.timedelta(days=rules.MISSING_LOST_DAYS)
    long_missing = db.scalars(
        sa.select(Copy).where(Copy.status == "missing", Copy.missing_since <= cutoff).order_by(Copy.id)
    ).all()
    for copy in long_missing:
        set_status(copy, "lost")
        copy.current_branch_id = None
        copy.missing_since = None
    db.flush()
    record(
        db,
        at=now,
        event="inventory_processed",
        actor_user_id=actor.id,
        entity_type="inventory",
        entity_id=None,
        details={
            "expired_counts": len(stale),
            "marked_lost": len(long_missing),
            "count_ids": [c.id for c in stale],
            "copy_ids": [c.id for c in long_missing],
        },
    )
    return len(stale), len(long_missing)

