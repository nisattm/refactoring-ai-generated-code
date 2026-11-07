"""E-book loans (LIB-DIG-15 to LIB-DIG-21)."""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.auth.models import User
from lms.core.errors import NotFound
from lms.core.timeutil import format_datetime
from lms.digital import state
from lms.digital.models import DigitalLoan, DigitalResource
from lms.digital.queue import move_queue
from lms.digital.rules import DEFAULT_LOAN_DAYS, DIGITAL_RULES, RENEW_WINDOW
from lms.members.models import Member


def get_loan_or_404(db: Session, loan_id: int) -> DigitalLoan:
    loan = db.get(DigitalLoan, loan_id)
    if loan is None:
        raise NotFound(f"Digital loan {loan_id} does not exist", details={"resource": "digital_loan", "id": loan_id})
    return loan


def _loan_period(resource: DigitalResource) -> datetime.timedelta:
    return datetime.timedelta(hours=24 * (resource.loan_days or DEFAULT_LOAN_DAYS))


def borrow(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    resource: DigitalResource,
    member: Member,
) -> DigitalLoan:
    """LIB-DIG-15 to LIB-DIG-17."""
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
    limit = DIGITAL_RULES[member.membership_type].loans
    if state.member_active_loans(db, member.id, now) >= limit:
        raise state.error("DIGITAL_LOAN_LIMIT_REACHED", "The member has reached the digital loan limit", limit=limit)
    if state.capacity_at(db, resource.id, now) == 0:
        raise state.error("NO_ACTIVE_LICENSE", "The resource has no active license")
    hold = state.usable_ready_hold(db, member.id, resource.id, now)
    if hold is None and state.free_copies(db, resource.id, now) == 0:
        raise state.error(
            "NO_COPY_AVAILABLE", "No copy is available", waiting=state.waiting_count(db, resource.id)
        )
    loan = DigitalLoan(
        resource_id=resource.id,
        member_id=member.id,
        hold_id=hold.id if hold is not None else None,
        borrowed_at=now,
        due_at=now + _loan_period(resource),
        renewed=False,
        status="open",
    )
    if hold is not None:
        hold.status = "fulfilled"
        hold.closed_at = now
    db.add(loan)
    db.flush()
    state.audit(
        db,
        now,
        actor.id,
        "digital_loan_created",
        "digital_loan",
        loan.id,
        resource_id=resource.id,
        member_id=member.id,
        hold_id=loan.hold_id,
        due_at=format_datetime(loan.due_at),
    )
    return loan


def return_loan(db: Session, now: datetime.datetime, actor: User, loan: DigitalLoan) -> DigitalLoan:
    """LIB-DIG-19."""
    if not loan.is_active(now):
        raise state.error("LOAN_NOT_OPEN", "The digital loan is not open", status=loan.effective_status(now))
    end_loan(db, now, actor.id, loan)
    resource = state.get_resource_or_404(db, loan.resource_id)
    move_queue(db, now, actor.id, resource)
    return loan


def end_loan(db: Session, now: datetime.datetime, actor_id: int | None, loan: DigitalLoan) -> None:
    """Store an active loan as returned now (used by returns and by member deactivation)."""
    loan.status = "returned"
    loan.ended_at = now
    state.audit(
        db,
        now,
        actor_id,
        "digital_loan_returned",
        "digital_loan",
        loan.id,
        resource_id=loan.resource_id,
        member_id=loan.member_id,
    )


def renew(db: Session, now: datetime.datetime, actor: User, loan: DigitalLoan) -> DigitalLoan:
    """LIB-DIG-21."""
    if not loan.is_active(now):
        raise state.error("LOAN_NOT_OPEN", "The digital loan is not open", status=loan.effective_status(now))
    if loan.renewed:
        raise state.error("RENEWAL_LIMIT_REACHED", "The loan was already renewed")
    renewable_from = loan.due_at - RENEW_WINDOW
    if now < renewable_from:
        raise state.error(
            "RENEWAL_TOO_EARLY", "The loan can be renewed 72 hours before it is due", renewable_from=format_datetime(renewable_from)
        )
    resource = state.get_resource_or_404(db, loan.resource_id)
    waiting = state.waiting_count(db, resource.id)
    if waiting > 0:
        raise state.error("RESOURCE_HAS_HOLDS", "The resource has waiting holds", waiting=waiting)
    if state.capacity_at(db, resource.id, now) == 0:
        raise state.error("NO_ACTIVE_LICENSE", "The resource has no active license")
    old_due = loan.due_at
    loan.due_at = loan.due_at + _loan_period(resource)
    loan.renewed = True
    loan.renewed_at = now
    state.audit(
        db,
        now,
        actor.id,
        "digital_loan_renewed",
        "digital_loan",
        loan.id,
        resource_id=resource.id,
        member_id=loan.member_id,
        due_at={"old": format_datetime(old_due), "new": format_datetime(loan.due_at)},
    )
    return loan


def loan_list_stmt(
    now: datetime.datetime,
    *,
    member_id: int | None = None,
    resource_id: int | None = None,
    status: str | None = None,
) -> sa.Select[tuple[DigitalLoan]]:
    """LIB-DIG-20; ``status`` is the status as shown (a finished open loan is ``expired``)."""
    stmt = sa.select(DigitalLoan).order_by(DigitalLoan.borrowed_at, DigitalLoan.id)
    if member_id is not None:
        stmt = stmt.where(DigitalLoan.member_id == member_id)
    if resource_id is not None:
        stmt = stmt.where(DigitalLoan.resource_id == resource_id)
    if status == "open":
        stmt = stmt.where(DigitalLoan.status == "open", DigitalLoan.due_at > now)
    elif status == "expired":
        stmt = stmt.where(
            sa.or_(DigitalLoan.status == "expired", sa.and_(DigitalLoan.status == "open", DigitalLoan.due_at <= now))
        )
    elif status == "returned":
        stmt = stmt.where(DigitalLoan.status == "returned")
    return stmt
