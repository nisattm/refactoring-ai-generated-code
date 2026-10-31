"""Transfers between branches (LIB-BR-05 to LIB-BR-09). The start of a transfer is ``start_transfer``."""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch, Transfer
from lms.branches.service import start_transfer
from lms.catalog.models import Copy
from lms.catalog.status import invalid_status
from lms.core.errors import Conflict, NotFound, reference_not_found
from lms.reservations import service as reservations
from lms.reservations.models import Reservation


def get_transfer_or_404(db: Session, transfer_id: int) -> Transfer:
    transfer = db.get(Transfer, transfer_id)
    if transfer is None:
        raise NotFound(f"Transfer {transfer_id} does not exist", details={"resource": "transfer", "id": transfer_id})
    return transfer


def relocate(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    *,
    copy_id: int,
    to_branch_id: int,
) -> Transfer:
    """LIB-BR-06."""
    copy = db.get(Copy, copy_id)
    if copy is None:
        raise reference_not_found("copy_id", copy_id)
    branch = db.get(Branch, to_branch_id)
    if branch is None:
        raise reference_not_found("to_branch_id", to_branch_id)
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive",
            code="BRANCH_INACTIVE",
            details={"field": "to_branch_id", "id": to_branch_id},
        )
    if copy.status != "available":
        raise invalid_status(copy, "relocate")
    if copy.current_branch_id == to_branch_id:
        raise Conflict(
            "The copy is already at the target branch", code="SAME_BRANCH", details={"branch_id": to_branch_id}
        )
    return start_transfer(db, now, actor.id, copy, to_branch_id, "relocation", holidays)


def process_arrivals(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date]
) -> int:
    """LIB-BR-07, LIB-BR-08: receive every ``in_transit`` transfer that is due."""
    today = now.date()
    due = db.scalars(
        sa.select(Transfer)
        .where(Transfer.status == "in_transit", Transfer.expected_on <= today)
        .order_by(Transfer.expected_on, Transfer.id)
    ).all()
    for transfer in due:
        copy = db.get(Copy, transfer.copy_id)
        assert copy is not None
        transfer.status = "received"
        transfer.received_on = today
        copy.current_branch_id = transfer.to_branch_id
        record(
            db,
            at=now,
            event="transfer_received",
            actor_user_id=actor.id,
            entity_type="transfer",
            entity_id=transfer.id,
            details={"copy_id": copy.id, "to_branch_id": transfer.to_branch_id, "reason": transfer.reason},
        )
        reservation = (
            db.get(Reservation, transfer.reservation_id)
            if transfer.reason == "reservation" and transfer.reservation_id is not None
            else None
        )
        if transfer.reason == "relocation":
            copy.home_branch_id = transfer.to_branch_id
        if reservation is not None and reservation.status == "in_transit":
            reservations.make_ready(db, now, reservation, copy, holidays, actor.id)
        else:
            reservations.release_copy(db, copy, now, holidays, actor.id)
    return len(due)


def transfer_list_stmt(
    *,
    status: str | None = None,
    copy_id: int | None = None,
    from_branch_id: int | None = None,
    to_branch_id: int | None = None,
    reason: str | None = None,
) -> sa.Select[tuple[Transfer]]:
    """LIB-BR-09: filtered transfers, newest first."""
    stmt = sa.select(Transfer).order_by(Transfer.id.desc())
    for column, value in (
        (Transfer.status, status),
        (Transfer.copy_id, copy_id),
        (Transfer.from_branch_id, from_branch_id),
        (Transfer.to_branch_id, to_branch_id),
        (Transfer.reason, reason),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    return stmt
