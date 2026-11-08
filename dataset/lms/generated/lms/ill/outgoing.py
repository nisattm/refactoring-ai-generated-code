"""Outgoing requests (LIB-ILL-24 to LIB-ILL-30)."""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.branches.service import require_active_branch
from lms.catalog.models import Book, Copy
from lms.catalog.release import release_copy
from lms.catalog.status import invalid_status, set_status
from lms.core.errors import Conflict, NotFound, ValidationFailed, reference_not_found
from lms.core.money import format_amount
from lms.ill import partners
from lms.ill.models import IllOutgoing
from lms.ill.rules import OUTGOING_DAYS
from lms.ill.schemas import OutgoingOut, outgoing_out


def get_outgoing_or_404(db: Session, outgoing_id: int) -> IllOutgoing:
    outgoing = db.get(IllOutgoing, outgoing_id)
    if outgoing is None:
        raise NotFound(
            f"Outgoing request {outgoing_id} does not exist", details={"resource": "ill_outgoing", "id": outgoing_id}
        )
    return outgoing


def _invalid_status(outgoing: IllOutgoing) -> Conflict:
    return Conflict(
        f"The request has status {outgoing.status}", code="INVALID_ILL_STATUS", details={"status": outgoing.status}
    )


def _event(db: Session, now: datetime.datetime, actor: User, event: str, outgoing: IllOutgoing, **details: object) -> None:
    record(
        db,
        at=now,
        event=event,
        actor_user_id=actor.id,
        entity_type="ill_outgoing",
        entity_id=outgoing.id,
        details={"partner_id": outgoing.partner_id, "book_id": outgoing.book_id, **details},
    )


def create_outgoing(db: Session, now: datetime.datetime, actor: User, *, partner_id: int, book_id: int) -> IllOutgoing:
    """LIB-ILL-24, LIB-ILL-27."""
    partner = partners.require_partner(db, partner_id)
    if db.get(Book, book_id) is None:
        raise reference_not_found("book_id", book_id)
    partners.require_active(partner)
    open_count = db.scalar(
        sa.select(sa.func.count()).select_from(IllOutgoing).where(
            IllOutgoing.partner_id == partner.id, IllOutgoing.status.in_(("requested", "shipped"))
        )
    )
    if (open_count or 0) >= partner.max_outgoing:
        raise Conflict(
            "The partner has reached the limit of open outgoing requests",
            code="PARTNER_LIMIT_REACHED",
            details={"limit": partner.max_outgoing},
        )
    outgoing = IllOutgoing(partner_id=partner.id, book_id=book_id, status="requested", created_at=now)
    db.add(outgoing)
    db.flush()
    _event(db, now, actor, "ill_outgoing_created", outgoing)
    return outgoing


def ship(db: Session, now: datetime.datetime, actor: User, outgoing: IllOutgoing, copy_id: int) -> IllOutgoing:
    """LIB-ILL-25."""
    copy = db.get(Copy, copy_id)
    if copy is None:
        raise reference_not_found("copy_id", copy_id)
    if outgoing.status != "requested":
        raise _invalid_status(outgoing)
    partner = partners.get_partner_or_404(db, outgoing.partner_id)
    partners.require_active(partner)
    today = now.date()
    overdue = db.scalar(
        sa.select(IllOutgoing.id)
        .where(IllOutgoing.partner_id == partner.id, IllOutgoing.status == "shipped", IllOutgoing.due_on < today)
        .limit(1)
    )
    if overdue is not None:
        raise Conflict(
            "The partner has an overdue outgoing request", code="PARTNER_HAS_OVERDUE", details={"id": overdue}
        )
    if copy.book_id != outgoing.book_id:
        raise ValidationFailed.single("copy_id", "the copy is not a copy of the requested book")
    if copy.status != "available":
        raise invalid_status(copy, "shipping to a partner")
    set_status(copy, "at_partner")
    outgoing.status = "shipped"
    outgoing.copy_id = copy.id
    outgoing.shipped_on = today
    outgoing.due_on = today + datetime.timedelta(days=OUTGOING_DAYS)
    _event(
        db, now, actor, "ill_outgoing_shipped", outgoing,
        copy_id=copy.id, shipped_on=today.isoformat(), due_on=outgoing.due_on.isoformat(),
    )
    return outgoing


def decline(db: Session, now: datetime.datetime, actor: User, outgoing: IllOutgoing) -> IllOutgoing:
    """LIB-ILL-26."""
    if outgoing.status != "requested":
        raise _invalid_status(outgoing)
    outgoing.status = "declined"
    _event(db, now, actor, "ill_outgoing_declined", outgoing)
    return outgoing


def returned(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    outgoing: IllOutgoing,
    branch_id: int,
) -> IllOutgoing:
    """LIB-ILL-28."""
    if db.get(Branch, branch_id) is None:
        raise reference_not_found("branch_id", branch_id)
    if outgoing.status != "shipped":
        raise _invalid_status(outgoing)
    require_active_branch(db, "branch_id", branch_id)
    copy = db.get(Copy, outgoing.copy_id)
    assert copy is not None
    outgoing.status = "returned"
    outgoing.returned_on = now.date()
    set_status(copy, "available")
    copy.current_branch_id = branch_id
    _event(db, now, actor, "ill_outgoing_returned", outgoing, copy_id=copy.id, branch_id=branch_id)
    release_copy(db, copy, now, holidays, actor.id)
    return outgoing


def report_lost(db: Session, now: datetime.datetime, actor: User, outgoing: IllOutgoing) -> IllOutgoing:
    """LIB-ILL-29."""
    if outgoing.status != "shipped":
        raise _invalid_status(outgoing)
    copy = db.get(Copy, outgoing.copy_id)
    assert copy is not None
    outgoing.status = "lost"
    outgoing.amount_due = copy.price
    outgoing.lost_on = now.date()
    set_status(copy, "lost")
    copy.current_branch_id = None
    _event(
        db, now, actor, "ill_outgoing_lost", outgoing, copy_id=copy.id, amount_due=format_amount(copy.price)
    )
    return outgoing


# --- queries ----------------------------------------------------------------------


def to_out(db: Session, outgoing: IllOutgoing, today: datetime.date) -> OutgoingOut:
    title = db.scalar(sa.select(Book.title).where(Book.id == outgoing.book_id)) or ""
    barcode = db.scalar(sa.select(Copy.barcode).where(Copy.id == outgoing.copy_id)) if outgoing.copy_id else None
    return outgoing_out(outgoing, today, title, barcode)


def outgoing_list_stmt(
    today: datetime.date, *, status: str | None = None, partner_id: int | None = None, overdue: bool | None = None
) -> sa.Select[tuple[IllOutgoing]]:
    """LIB-ILL-30."""
    stmt = sa.select(IllOutgoing).order_by(IllOutgoing.created_at, IllOutgoing.id)
    if status is not None:
        stmt = stmt.where(IllOutgoing.status == status)
    if partner_id is not None:
        stmt = stmt.where(IllOutgoing.partner_id == partner_id)
    if overdue is not None:
        is_over = sa.and_(IllOutgoing.status == "shipped", IllOutgoing.due_on < today)
        stmt = stmt.where(is_over if overdue else sa.not_(is_over))
    return stmt
