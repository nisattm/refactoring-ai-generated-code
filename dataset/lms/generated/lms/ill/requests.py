"""Incoming requests (LIB-ILL-05 to LIB-ILL-23)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.branches.service import require_active_branch
from lms.catalog.models import Book, Copy
from lms.core.errors import Conflict, NotFound, ValidationFailed, reference_not_found
from lms.core.money import ZERO, format_amount
from lms.fines import service as fines
from lms.fines.schemas import BLOCKING_DEBT
from lms.ill import partners
from lms.ill.accrual import is_overdue, late_fee_on
from lms.ill.models import OPEN_STATUSES, IllOutgoing, IllRequest, IllRequestAction
from lms.ill.rules import COLLECT_DAYS, MAX_TRIED_PARTNERS, MIN_PERIOD_DAYS, OPEN_LIMITS, member_due_on
from lms.loans.models import Loan
from lms.members.models import Member
from lms.notifications.service import notify_ill


def get_request_or_404(db: Session, request_id: int) -> IllRequest:
    request = db.get(IllRequest, request_id)
    if request is None:
        raise NotFound(
            f"Interlibrary request {request_id} does not exist", details={"resource": "ill_request", "id": request_id}
        )
    return request


def _invalid_status(request: IllRequest) -> Conflict:
    return Conflict(
        f"The request has status {request.status}", code="INVALID_ILL_STATUS", details={"status": request.status}
    )


def _event(db: Session, now: datetime.datetime, actor_id: int | None, event: str, request: IllRequest, **details: object) -> None:
    record(
        db,
        at=now,
        event=event,
        actor_user_id=actor_id,
        entity_type="ill_request",
        entity_id=request.id,
        details={"member_id": request.member_id, **details},
    )


# --- member checks ----------------------------------------------------------------


def _total_debt(db: Session, member: Member, now: datetime.datetime, holidays: Container[datetime.date]) -> Decimal:
    return fines.outstanding_fees(db, member.id) + fines.accrued_late_fees(db, member.id, now, holidays)


def _check_standing(db: Session, member: Member, now: datetime.datetime, holidays: Container[datetime.date]) -> None:
    """LIB-ILL-06 checks (1) and (2)."""
    if member.status == "passive":
        raise Conflict("The member is passive", code="MEMBER_PASSIVE")
    if now.date() > member.valid_until:
        raise Conflict("The membership has expired", code="MEMBERSHIP_EXPIRED")


def _check_debt_and_overdue(
    db: Session, member: Member, now: datetime.datetime, holidays: Container[datetime.date]
) -> None:
    """LIB-ILL-06 checks (4) and (5)."""
    debt = _total_debt(db, member, now, holidays)
    if debt >= BLOCKING_DEBT:
        raise Conflict(
            "The member's debt is too high", code="MEMBER_BLOCKED_BY_DEBT", details={"total_debt": format_amount(debt)}
        )
    today = now.date()
    overdue_loan = db.scalar(
        sa.select(Loan.id).where(Loan.member_id == member.id, Loan.status == "open", Loan.due_date < today).limit(1)
    )
    overdue_request = db.scalar(
        sa.select(IllRequest.id)
        .where(IllRequest.member_id == member.id, IllRequest.status == "on_loan", IllRequest.due_on < today)
        .limit(1)
    )
    if overdue_loan is not None or overdue_request is not None:
        raise Conflict("The member has an overdue loan", code="MEMBER_HAS_OVERDUE")


# --- creation ---------------------------------------------------------------------


def create_request(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    member: Member,
    *,
    title: str,
    author: str,
    isbn: str | None,
) -> IllRequest:
    """LIB-ILL-05, LIB-ILL-06."""
    _check_standing(db, member, now, holidays)
    if member.membership_type == "guest":
        raise Conflict("Guests cannot make interlibrary requests", code="ILL_NOT_ALLOWED_FOR_TYPE")
    _check_debt_and_overdue(db, member, now, holidays)
    limit = OPEN_LIMITS[member.membership_type]
    open_count = db.scalar(
        sa.select(sa.func.count()).select_from(IllRequest).where(
            IllRequest.member_id == member.id, IllRequest.status.in_(OPEN_STATUSES)
        )
    )
    if (open_count or 0) >= limit:
        raise Conflict("The limit of open requests is reached", code="ILL_LIMIT_REACHED", details={"limit": limit})
    if isbn is not None:
        local = db.scalar(
            sa.select(Book.id)
            .where(Book.isbn == isbn, Book.id.in_(sa.select(Copy.book_id).where(Copy.status == "available")))
            .order_by(Book.id)
            .limit(1)
        )
        if local is not None:
            raise Conflict("The book is available locally", code="AVAILABLE_LOCALLY", details={"book_id": local})
        duplicate = db.scalar(
            sa.select(IllRequest.id).where(
                IllRequest.member_id == member.id, IllRequest.isbn == isbn, IllRequest.status.in_(OPEN_STATUSES)
            ).limit(1)
        )
        if duplicate is not None:
            raise Conflict(
                "The member has an open request for this ISBN", code="DUPLICATE_ILL_REQUEST", details={"id": duplicate}
            )

    request = IllRequest(
        member_id=member.id,
        title=title,
        author=author,
        isbn=isbn,
        status="requested",
        tried_partner_ids=[],
        renewal="none",
        created_at=now,
    )
    db.add(request)
    db.flush()
    _event(db, now, actor.id, "ill_request_created", request, title=title, author=author, isbn=isbn)
    return request


# --- staff steps ------------------------------------------------------------------


def send(db: Session, now: datetime.datetime, actor: User, request: IllRequest, partner_id: int) -> IllRequest:
    """LIB-ILL-07."""
    partner = partners.require_partner(db, partner_id)
    if request.status not in ("requested", "rejected"):
        raise _invalid_status(request)
    partners.require_active(partner)
    tried = list(request.tried_partner_ids or [])
    if partner.id in tried:
        raise Conflict(
            "The request was already sent to this partner", code="PARTNER_ALREADY_TRIED", details={"id": partner.id}
        )
    if len(tried) >= MAX_TRIED_PARTNERS:
        raise Conflict(
            "The request was already sent to three partners",
            code="ILL_TRY_LIMIT_REACHED",
            details={"limit": MAX_TRIED_PARTNERS},
        )
    request.status = "sent"
    request.partner_id = partner.id
    request.tried_partner_ids = [*tried, partner.id]
    request.stored_request_fee = partner.request_fee
    request.stored_daily_late_fee = partner.daily_late_fee
    db.add(IllRequestAction(request_id=request.id, partner_id=partner.id, action="sent", on_date=now.date()))
    db.flush()
    _event(db, now, actor.id, "ill_request_sent", request, partner_id=partner.id)
    return request


def reject(db: Session, now: datetime.datetime, actor: User, request: IllRequest, reason: str) -> IllRequest:
    """LIB-ILL-08."""
    if request.status != "sent":
        raise _invalid_status(request)
    assert request.partner_id is not None
    request.status = "rejected"
    request.reject_reason = reason
    db.add(IllRequestAction(request_id=request.id, partner_id=request.partner_id, action="rejected", on_date=now.date()))
    db.flush()
    _event(db, now, actor.id, "ill_request_rejected", request, partner_id=request.partner_id, reason=reason)
    notify_ill(
        db, now, request.member_id, "ill_request_rejected",
        f'Your interlibrary request for "{request.title}" was rejected by the partner library: {reason}.',
        ill_request_id=request.id,
    )
    return request


def cancel(
    db: Session, now: datetime.datetime, actor: User, request: IllRequest, *, reason: str
) -> IllRequest:
    """LIB-ILL-09. ``reason`` is ``member_request``, ``staff_request`` or ``member_deactivated``."""
    if request.status not in ("requested", "sent", "rejected"):
        raise _invalid_status(request)
    request.status = "cancelled"
    request.cancel_reason = reason
    request.closed_on = now.date()
    _event(db, now, actor.id, "ill_request_cancelled", request, reason=reason)
    if reason in ("staff_request", "member_deactivated"):
        notify_ill(
            db, now, request.member_id, "ill_request_cancelled",
            f'Your interlibrary request for "{request.title}" was cancelled ({reason}).',
            ill_request_id=request.id,
        )
    return request


def receive(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    request: IllRequest,
    *,
    partner_due_on: datetime.date,
    replacement_cost: Decimal,
    pickup_branch_id: int,
) -> IllRequest:
    """LIB-ILL-10, LIB-ILL-11."""
    branch = db.get(Branch, pickup_branch_id)
    if branch is None:
        raise reference_not_found("pickup_branch_id", pickup_branch_id)
    if request.status != "sent":
        raise _invalid_status(request)
    require_active_branch(db, "pickup_branch_id", pickup_branch_id)
    today = now.date()
    due_on = member_due_on(partner_due_on, holidays)
    if due_on < today + datetime.timedelta(days=MIN_PERIOD_DAYS):
        raise Conflict(
            "The loan period is too short", code="ILL_PERIOD_TOO_SHORT", details={"due_on": due_on.isoformat()}
        )
    request.status = "received"
    request.received_on = today
    request.collect_until = today + datetime.timedelta(days=COLLECT_DAYS)
    request.partner_due_on = partner_due_on
    request.due_on = due_on
    request.replacement_cost = replacement_cost
    request.pickup_branch_id = pickup_branch_id
    _event(
        db, now, actor.id, "ill_request_received", request,
        pickup_branch_id=pickup_branch_id,
        partner_due_on=partner_due_on.isoformat(),
        due_on=due_on.isoformat(),
        replacement_cost=format_amount(replacement_cost),
    )
    notify_ill(
        db, now, request.member_id, "ill_request_received",
        f'Your interlibrary request "{request.title}" has arrived. Collect it at {branch.name} '
        f"until {request.collect_until.isoformat()}.",
        ill_request_id=request.id,
    )
    return request


def collect(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date], request: IllRequest
) -> IllRequest:
    """LIB-ILL-13, LIB-ILL-14."""
    if request.status != "received":
        raise _invalid_status(request)
    today = now.date()
    assert request.collect_until is not None
    if today > request.collect_until:
        raise Conflict(
            "The collection period is over",
            code="ILL_COLLECT_PERIOD_OVER",
            details={"collect_until": request.collect_until.isoformat()},
        )
    member = db.get(Member, request.member_id)
    assert member is not None
    _check_standing(db, member, now, holidays)
    _check_debt_and_overdue(db, member, now, holidays)
    request.status = "on_loan"
    request.collected_on = today
    _event(db, now, actor.id, "ill_request_collected", request, due_on=request.due_on.isoformat() if request.due_on else None)
    fee = request.stored_request_fee or ZERO
    if fee > ZERO:
        fines.create_fee(
            db, now, actor, member_id=request.member_id, loan_id=None, kind="ill_request_fee", amount=fee,
            ill_request_id=request.id,
        )
    return request


def renewal_request(db: Session, now: datetime.datetime, actor: User, request: IllRequest) -> IllRequest:
    """LIB-ILL-15."""
    if request.status != "on_loan":
        raise _invalid_status(request)
    if is_overdue(request, now.date()):
        assert request.due_on is not None
        raise Conflict("The request is overdue", code="ILL_OVERDUE", details={"due_on": request.due_on.isoformat()})
    if request.renewal != "none":
        raise Conflict(
            "A renewal was already requested",
            code="ILL_RENEWAL_ALREADY_REQUESTED",
            details={"renewal": request.renewal},
        )
    request.renewal = "requested"
    _event(db, now, actor.id, "ill_renewal_requested", request)
    return request


def renewal_answer(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    request: IllRequest,
    *,
    approved: bool,
    partner_due_on: datetime.date | None,
) -> IllRequest:
    """LIB-ILL-16."""
    if request.renewal != "requested":
        raise Conflict(
            "No renewal was requested", code="ILL_NO_RENEWAL_REQUESTED", details={"renewal": request.renewal}
        )
    if approved:
        assert partner_due_on is not None
        if request.partner_due_on is not None and partner_due_on <= request.partner_due_on:
            raise ValidationFailed.single("partner_due_on", "partner_due_on must be later than the current one")
        request.renewal = "approved"
        request.partner_due_on = partner_due_on
        request.due_on = member_due_on(partner_due_on, holidays)
        message = (
            f'The renewal of your interlibrary loan "{request.title}" was approved. '
            f"The new due date is {request.due_on.isoformat()}."
        )
    else:
        request.renewal = "refused"
        message = f'The renewal of your interlibrary loan "{request.title}" was refused.'
    _event(
        db, now, actor.id, "ill_renewal_answered", request,
        approved=approved,
        partner_due_on=request.partner_due_on.isoformat() if request.partner_due_on else None,
        due_on=request.due_on.isoformat() if request.due_on else None,
    )
    notify_ill(db, now, request.member_id, "ill_renewal_answered", message, ill_request_id=request.id)
    return request


def return_request(
    db: Session, now: datetime.datetime, actor: User, request: IllRequest, branch_id: int
) -> IllRequest:
    """LIB-ILL-17, LIB-ILL-18."""
    if db.get(Branch, branch_id) is None:
        raise reference_not_found("branch_id", branch_id)
    if request.status != "on_loan":
        raise _invalid_status(request)
    require_active_branch(db, "branch_id", branch_id)
    today = now.date()
    request.status = "returned"
    request.returned_on = today
    late_fee = late_fee_on(request, today)
    _event(
        db, now, actor.id, "ill_request_returned", request,
        branch_id=branch_id, late_fee=format_amount(late_fee),
    )
    if late_fee > ZERO:
        fines.create_fee(
            db, now, actor, member_id=request.member_id, loan_id=None, kind="ill_late_fee", amount=late_fee,
            ill_request_id=request.id,
        )
    return request


def close(db: Session, now: datetime.datetime, actor: User, request: IllRequest) -> IllRequest:
    """LIB-ILL-20."""
    if request.status not in ("returned", "uncollected"):
        raise _invalid_status(request)
    request.status = "closed"
    request.closed_on = now.date()
    _event(db, now, actor.id, "ill_request_closed", request)
    return request


def report_lost(db: Session, now: datetime.datetime, actor: User, request: IllRequest) -> IllRequest:
    """LIB-ILL-21."""
    if request.status != "on_loan":
        raise _invalid_status(request)
    today = now.date()
    assert request.replacement_cost is not None
    late_fee = late_fee_on(request, today) if is_overdue(request, today) else ZERO
    request.status = "lost"
    request.closed_on = today
    _event(
        db, now, actor.id, "ill_request_lost", request,
        replacement_cost=format_amount(request.replacement_cost), late_fee=format_amount(late_fee),
    )
    if late_fee > ZERO:
        fines.create_fee(
            db, now, actor, member_id=request.member_id, loan_id=None, kind="ill_late_fee", amount=late_fee,
            ill_request_id=request.id,
        )
    fines.create_fee(
        db, now, actor, member_id=request.member_id, loan_id=None, kind="ill_lost", amount=request.replacement_cost,
        ill_request_id=request.id,
    )
    return request


def process(db: Session, now: datetime.datetime, actor: User) -> tuple[int, int]:
    """LIB-ILL-22: mark uncollected requests; returns the count and the number of overdue outgoing requests."""
    today = now.date()
    stale = db.scalars(
        sa.select(IllRequest).where(IllRequest.status == "received", IllRequest.collect_until < today).order_by(IllRequest.id)
    ).all()
    for request in stale:
        request.status = "uncollected"
        _event(db, now, actor.id, "ill_request_uncollected", request, collect_until=request.collect_until.isoformat())
        notify_ill(
            db, now, request.member_id, "ill_request_uncollected",
            f'Your interlibrary request "{request.title}" was not collected by '
            f"{request.collect_until.isoformat()} and goes back to the partner library.",
            ill_request_id=request.id,
        )
    overdue_outgoing = db.scalar(
        sa.select(sa.func.count()).select_from(IllOutgoing).where(IllOutgoing.status == "shipped", IllOutgoing.due_on < today)
    )
    return len(stale), overdue_outgoing or 0


# --- effects on member deactivation (LIB-ILL-32) ----------------------------------


def has_open_receipt(db: Session, member_id: int) -> bool:
    stmt = sa.select(IllRequest.id).where(IllRequest.member_id == member_id, IllRequest.status.in_(("received", "on_loan")))
    return db.scalar(stmt.limit(1)) is not None


def cancel_for_deactivation(db: Session, now: datetime.datetime, actor: User, member_id: int) -> None:
    stmt = (
        sa.select(IllRequest)
        .where(IllRequest.member_id == member_id, IllRequest.status.in_(("requested", "sent", "rejected")))
        .order_by(IllRequest.id)
    )
    for request in db.scalars(stmt).all():
        cancel(db, now, actor, request, reason="member_deactivated")


# --- queries ----------------------------------------------------------------------


def request_list_stmt(
    today: datetime.date,
    *,
    member_id: int | None = None,
    status: str | None = None,
    partner_id: int | None = None,
    overdue: bool | None = None,
) -> sa.Select[tuple[IllRequest]]:
    """LIB-ILL-23."""
    stmt = sa.select(IllRequest).order_by(IllRequest.created_at, IllRequest.id)
    if member_id is not None:
        stmt = stmt.where(IllRequest.member_id == member_id)
    if status is not None:
        stmt = stmt.where(IllRequest.status == status)
    if partner_id is not None:
        stmt = stmt.where(IllRequest.partner_id == partner_id)
    if overdue is not None:
        is_over = sa.and_(IllRequest.status == "on_loan", IllRequest.due_on < today)
        stmt = stmt.where(is_over if overdue else sa.not_(is_over))
    return stmt
