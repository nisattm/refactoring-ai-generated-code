"""Business logic of module 6: reservations (LIB-RES-01 to LIB-RES-14).

Also holds the release procedure (LIB-RES-08) that other modules call when a copy becomes free.
"""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.branches.service import start_transfer
from lms.catalog.models import Book, Copy
from lms.catalog.status import GONE_STATUSES, set_status
from lms.core.calendar import add_working_days
from lms.core.errors import Conflict, NotFound, reference_not_found
from lms.loans.models import Loan
from lms.members.models import Member
from lms.notifications.service import notify_reservation
from lms.reservations.models import ACTIVE_STATUSES, Reservation

RESERVATION_LIMIT = 3
HOLD_WORKING_DAYS = 3


def get_reservation_or_404(db: Session, reservation_id: int) -> Reservation:
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise NotFound(
            f"Reservation {reservation_id} does not exist",
            details={"resource": "reservation", "id": reservation_id},
        )
    return reservation


_NOTIFIED_EVENTS = frozenset({"reservation_ready", "reservation_in_transit", "reservation_expired"})


def _emit(
    db: Session,
    now: datetime.datetime,
    event: str,
    reservation: Reservation,
    actor_user_id: int | None,
    **extra: Any,
) -> None:
    """Report a reservation event (section 13) to the audit log and, where LIB-NOT-01 says so, notify the member."""
    details: dict[str, Any] = {
        "book_id": reservation.book_id,
        "member_id": reservation.member_id,
        "pickup_branch_id": reservation.pickup_branch_id,
        "copy_id": reservation.copy_id,
    }
    details.update(extra)
    record(
        db,
        at=now,
        event=event,
        actor_user_id=actor_user_id,
        entity_type="reservation",
        entity_id=reservation.id,
        details=details,
    )
    if event in _NOTIFIED_EVENTS or (event == "reservation_cancelled" and extra.get("reason") != "member_request"):
        notify_reservation(db, now, event, reservation)


# --- queries used by other modules ----------------------------------------------


def count_active(db: Session, member_id: int) -> int:
    """Active reservations (``waiting``, ``in_transit``, ``ready``) of a member."""
    stmt = sa.select(sa.func.count()).select_from(Reservation).where(
        Reservation.member_id == member_id, Reservation.status.in_(ACTIVE_STATUSES)
    )
    return db.scalar(stmt) or 0


def book_has_active_reservation(db: Session, book_id: int) -> bool:
    """LIB-LOAN-07: any member has an active reservation for the book."""
    stmt = sa.select(Reservation.id).where(Reservation.book_id == book_id, Reservation.status.in_(ACTIVE_STATUSES))
    return db.scalar(stmt.limit(1)) is not None


def queue_position(db: Session, reservation: Reservation) -> int | None:
    """``ReservationOut.queue_position``: 1 + earlier ``waiting`` reservations of the same book."""
    if reservation.status != "waiting":
        return None
    earlier = sa.or_(
        Reservation.created_at < reservation.created_at,
        sa.and_(Reservation.created_at == reservation.created_at, Reservation.id < reservation.id),
    )
    stmt = sa.select(sa.func.count()).select_from(Reservation).where(
        Reservation.book_id == reservation.book_id, Reservation.status == "waiting", earlier
    )
    return 1 + (db.scalar(stmt) or 0)


def _queue_order() -> tuple[Any, Any]:
    return Reservation.created_at, Reservation.id


def _first_waiting(db: Session, book_id: int) -> Reservation | None:
    stmt = sa.select(Reservation).where(Reservation.book_id == book_id, Reservation.status == "waiting")
    return db.scalars(stmt.order_by(*_queue_order()).limit(1)).first()


# --- release procedure -------------------------------------------------------------


def make_ready(
    db: Session,
    now: datetime.datetime,
    reservation: Reservation,
    copy: Copy,
    holidays: Container[datetime.date],
    actor_user_id: int | None,
) -> None:
    """LIB-RES-09: the copy is held at its current branch for the reservation."""
    today = now.date()
    reservation.status = "ready"
    reservation.copy_id = copy.id
    reservation.ready_on = today
    reservation.hold_until = add_working_days(today, HOLD_WORKING_DAYS, holidays)
    set_status(copy, "on_hold")
    _emit(
        db,
        now,
        "reservation_ready",
        reservation,
        actor_user_id,
        ready_on=today.isoformat(),
        hold_until=reservation.hold_until.isoformat(),
    )


def release_copy(
    db: Session,
    copy: Copy,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    actor_user_id: int | None = None,
) -> None:
    """LIB-RES-08: a copy became free; the first waiting reservation of its book takes it."""
    reservation = _first_waiting(db, copy.book_id)
    if reservation is None:
        if copy.current_branch_id == copy.home_branch_id:
            if copy.status != "available":
                set_status(copy, "available")
        else:
            start_transfer(db, now, actor_user_id, copy, copy.home_branch_id, "return_home", holidays)
    elif reservation.pickup_branch_id == copy.current_branch_id:
        make_ready(db, now, reservation, copy, holidays, actor_user_id)
    else:
        reservation.status = "in_transit"
        reservation.copy_id = copy.id
        start_transfer(
            db, now, actor_user_id, copy, reservation.pickup_branch_id, "reservation", holidays, reservation.id
        )
        _emit(db, now, "reservation_in_transit", reservation, actor_user_id)


# --- creation ------------------------------------------------------------------------


def create_reservation(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    *,
    member_id: int,
    book_id: int,
    pickup_branch_id: int,
) -> Reservation:
    """LIB-RES-01, LIB-RES-02, LIB-RES-05."""
    branch = db.get(Branch, pickup_branch_id)
    if branch is None:
        raise reference_not_found("pickup_branch_id", pickup_branch_id)
    book = db.get(Book, book_id)
    if book is None:
        raise reference_not_found("book_id", book_id)
    member = db.get(Member, member_id)
    if member is None:
        raise reference_not_found("member_id", member_id)

    if not branch.is_active:  # LIB-BR-04: before all other 409 checks
        raise Conflict(
            f"Branch {branch.code} is inactive",
            code="BRANCH_INACTIVE",
            details={"field": "pickup_branch_id", "id": pickup_branch_id},
        )
    today = now.date()
    if member.status == "passive":
        raise Conflict("The member is passive", code="MEMBER_PASSIVE")
    if today > member.valid_until:
        raise Conflict("The membership has expired", code="MEMBERSHIP_EXPIRED")
    lendable = sa.select(Copy.id).where(Copy.book_id == book_id, Copy.status.not_in(GONE_STATUSES)).limit(1)
    if db.scalar(lendable) is None:
        raise Conflict("The book has no copy that can be lent", code="BOOK_NOT_LENDABLE", details={"book_id": book_id})
    duplicate = sa.select(Reservation.id).where(
        Reservation.member_id == member_id, Reservation.book_id == book_id, Reservation.status.in_(ACTIVE_STATUSES)
    )
    if db.scalar(duplicate.limit(1)) is not None:
        raise Conflict(
            "The member already has an active reservation for this book",
            code="DUPLICATE_RESERVATION",
            details={"book_id": book_id},
        )
    borrowed = (
        sa.select(Loan.id)
        .join(Copy, Copy.id == Loan.copy_id)
        .where(Loan.member_id == member_id, Loan.status == "open", Copy.book_id == book_id)
    )
    if db.scalar(borrowed.limit(1)) is not None:
        raise Conflict(
            "The member has already borrowed a copy of this book",
            code="ALREADY_BORROWED",
            details={"book_id": book_id},
        )
    if count_active(db, member_id) >= RESERVATION_LIMIT:
        raise Conflict(
            "The member has reached the reservation limit",
            code="RESERVATION_LIMIT_REACHED",
            details={"limit": RESERVATION_LIMIT},
        )
    at_pickup = sa.select(Copy.id).where(
        Copy.book_id == book_id, Copy.status == "available", Copy.current_branch_id == pickup_branch_id
    )
    if db.scalar(at_pickup.limit(1)) is not None:
        raise Conflict(
            "A copy is available at the pickup branch",
            code="COPY_AVAILABLE_AT_BRANCH",
            details={"pickup_branch_id": pickup_branch_id},
        )

    reservation = Reservation(
        book_id=book_id, member_id=member_id, pickup_branch_id=pickup_branch_id, status="waiting", created_at=now
    )
    db.add(reservation)
    db.flush()
    _emit(db, now, "reservation_created", reservation, actor.id)

    # LIB-RES-05: a copy that is available at another branch is assigned at once.
    available = db.scalars(
        sa.select(Copy).where(Copy.book_id == book_id, Copy.status == "available").order_by(Copy.id)
    ).all()
    for copy in available:
        if _first_waiting(db, book_id) is None:
            break
        release_copy(db, copy, now, holidays, actor.id)
    return reservation


# --- closing -------------------------------------------------------------------------


def _held_copy(db: Session, reservation: Reservation) -> Copy | None:
    return db.get(Copy, reservation.copy_id) if reservation.copy_id is not None else None


def _cancel(
    db: Session, now: datetime.datetime, actor_user_id: int | None, reservation: Reservation, reason: str
) -> Copy | None:
    """Mark the reservation cancelled; returns the held copy that must be released (if it was ``ready``)."""
    was_ready = reservation.status == "ready"
    reservation.status = "cancelled"
    reservation.closed_at = now
    reservation.cancel_reason = reason
    _emit(db, now, "reservation_cancelled", reservation, actor_user_id, reason=reason)
    return _held_copy(db, reservation) if was_ready else None


def cancel_reservation(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    reservation: Reservation,
    reason: str,
) -> Reservation:
    """LIB-RES-13."""
    if not reservation.is_active:
        raise Conflict(
            "The reservation is not active", code="RESERVATION_NOT_ACTIVE", details={"status": reservation.status}
        )
    copy = _cancel(db, now, actor.id, reservation, reason)
    if copy is not None:
        release_copy(db, copy, now, holidays, actor.id)
    return reservation


def cancel_for_deactivation(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date], member: Member
) -> None:
    """LIB-MEM-10: all active reservations of the member are cancelled (``member_deactivated``)."""
    active = db.scalars(
        sa.select(Reservation)
        .where(Reservation.member_id == member.id, Reservation.status.in_(ACTIVE_STATUSES))
        .order_by(Reservation.id)
    ).all()
    held = [copy for r in active if (copy := _cancel(db, now, actor.id, r, "member_deactivated")) is not None]
    for copy in held:  # release only after all are cancelled, so none of them is offered the copy again
        release_copy(db, copy, now, holidays, actor.id)


def _expire(
    db: Session,
    now: datetime.datetime,
    actor_user_id: int | None,
    holidays: Container[datetime.date],
    reservation: Reservation,
) -> None:
    """LIB-RES-11: a ``ready`` reservation past ``hold_until`` expires and its copy is released."""
    copy = _held_copy(db, reservation)
    reservation.status = "expired"
    reservation.closed_at = now
    _emit(db, now, "reservation_expired", reservation, actor_user_id)
    if copy is not None:
        release_copy(db, copy, now, holidays, actor_user_id)


def _is_stale(reservation: Reservation, today: datetime.date) -> bool:
    return reservation.status == "ready" and reservation.hold_until is not None and today > reservation.hold_until


def process_expired(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date]
) -> int:
    """LIB-RES-11: expire every ``ready`` reservation whose hold has passed."""
    stale = db.scalars(
        sa.select(Reservation)
        .where(Reservation.status == "ready", Reservation.hold_until < now.date())
        .order_by(Reservation.book_id, *_queue_order())
    ).all()
    for reservation in stale:
        _expire(db, now, actor.id, holidays, reservation)
    return len(stale)


def expire_stale_hold(
    db: Session,
    now: datetime.datetime,
    copy: Copy,
    holidays: Container[datetime.date],
    actor_user_id: int | None,
) -> None:
    """LIB-RES-11: before an ``on_hold`` copy is lent, its reservation expires if it is past ``hold_until``."""
    if copy.status != "on_hold":
        return
    reservation = db.scalar(
        sa.select(Reservation).where(Reservation.copy_id == copy.id, Reservation.status == "ready")
    )
    if reservation is not None and _is_stale(reservation, now.date()):
        _expire(db, now, actor_user_id, holidays, reservation)


# --- lending -------------------------------------------------------------------------


def hold_belongs_to_member(db: Session, now: datetime.datetime, copy: Copy, member: Member) -> bool:
    """LIB-LOAN-05 step 6: the ``on_hold`` copy is held by a ``ready`` reservation of the member that has not
    passed ``hold_until`` (callers expire stale holds first, LIB-RES-11)."""
    reservation = db.scalar(
        sa.select(Reservation).where(
            Reservation.copy_id == copy.id, Reservation.member_id == member.id, Reservation.status == "ready"
        )
    )
    return reservation is not None and not _is_stale(reservation, now.date())


def fulfil_for_loan(
    db: Session,
    now: datetime.datetime,
    member: Member,
    copy: Copy,
    holidays: Container[datetime.date],
    actor_user_id: int | None = None,
) -> None:
    """LIB-RES-10: the member's active reservation for the book of ``copy`` becomes ``fulfilled``."""
    reservation = db.scalar(
        sa.select(Reservation).where(
            Reservation.member_id == member.id,
            Reservation.book_id == copy.book_id,
            Reservation.status.in_(ACTIVE_STATUSES),
        )
    )
    if reservation is None:
        return
    if _is_stale(reservation, now.date()):  # a hold past its date is expired, not fulfilled
        _expire(db, now, actor_user_id, holidays, reservation)
        return
    held = _held_copy(db, reservation) if reservation.status == "ready" else None
    reservation.status = "fulfilled"
    reservation.closed_at = now
    _emit(db, now, "reservation_fulfilled", reservation, actor_user_id, lent_copy_id=copy.id)
    if held is not None and held.id != copy.id:
        release_copy(db, held, now, holidays, actor_user_id)
