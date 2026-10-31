"""Business logic of module 8: notifications (LIB-NOT-01 to LIB-NOT-07).

Other modules call the ``notify_*`` functions in the transaction of the event they report.
"""

from __future__ import annotations

import datetime
from collections.abc import Container
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.catalog.models import Book, Copy
from lms.core.calendar import add_working_days
from lms.core.errors import NotFound
from lms.core.money import format_amount
from lms.fines.models import Fee
from lms.loans.models import Loan
from lms.notifications.models import Notification
from lms.reservations.models import Reservation


def get_notification_or_404(db: Session, notification_id: int) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise NotFound(
            f"Notification {notification_id} does not exist",
            details={"resource": "notification", "id": notification_id},
        )
    return notification


def _create(
    db: Session,
    now: datetime.datetime,
    member_id: int,
    type_: str,
    message: str,
    *,
    loan_id: int | None = None,
    reservation_id: int | None = None,
    fee_id: int | None = None,
    reminder_date: datetime.date | None = None,
) -> Notification:
    notification = Notification(
        member_id=member_id,
        type=type_,
        message=message,
        loan_id=loan_id,
        reservation_id=reservation_id,
        fee_id=fee_id,
        created_at=now,
        reminder_date=reminder_date,
    )
    db.add(notification)
    db.flush()
    return notification


def _title_of_book(db: Session, book_id: int) -> str:
    title = db.scalar(sa.select(Book.title).where(Book.id == book_id))
    return title if title is not None else f"book {book_id}"


def _title_of_loan(db: Session, loan: Loan) -> str:
    book_id = db.scalar(sa.select(Copy.book_id).where(Copy.id == loan.copy_id))
    return _title_of_book(db, book_id) if book_id is not None else f"copy {loan.copy_id}"


# --- loans -----------------------------------------------------------------------


def notify_loan(db: Session, now: datetime.datetime, type_: str, loan: Loan) -> Notification:
    """``loan_created``, ``loan_renewed``, ``loan_returned`` and ``loan_lost``."""
    title = _title_of_loan(db, loan)
    due = loan.due_date.isoformat()
    message = {
        "loan_created": f'You borrowed "{title}". It is due on {due}.',
        "loan_renewed": f'Your loan of "{title}" was renewed. The new due date is {due}.',
        "loan_returned": f'You returned "{title}" (due date {due}).',
        "loan_lost": f'Your loan of "{title}" (due date {due}) was reported as lost.',
    }[type_]
    return _create(db, now, loan.member_id, type_, message, loan_id=loan.id)


# --- reservations ----------------------------------------------------------------


def notify_reservation(db: Session, now: datetime.datetime, type_: str, reservation: Reservation) -> Notification:
    """``reservation_ready``, ``reservation_in_transit``, ``reservation_expired`` and ``reservation_cancelled``."""
    title = _title_of_book(db, reservation.book_id)
    hold = reservation.hold_until.isoformat() if reservation.hold_until is not None else None
    if type_ == "reservation_ready":
        message = f'Your reservation of "{title}" is ready for pickup until {hold}.'
    elif type_ == "reservation_in_transit":
        message = f'A copy of "{title}" is on its way to your pickup branch.'
    elif type_ == "reservation_expired":
        message = f'Your reservation of "{title}" expired because it was not collected by {hold}.'
    else:
        reason = reservation.cancel_reason
        message = f'Your reservation of "{title}" was cancelled ({reason}).'
        if hold is not None:
            message += f" The hold ran until {hold}."
    return _create(db, now, reservation.member_id, type_, message, reservation_id=reservation.id)


# --- fees and payments -----------------------------------------------------------


def notify_fee_created(db: Session, now: datetime.datetime, fee: Fee) -> Notification:
    message = f"A {fee.kind.replace('_', ' ')} of {format_amount(fee.amount)} TRY was added to your account."
    return _create(db, now, fee.member_id, "fee_created", message, loan_id=fee.loan_id, fee_id=fee.id)


def notify_payment_received(db: Session, now: datetime.datetime, member_id: int, amount: Decimal) -> Notification:
    message = f"Your payment of {format_amount(amount)} TRY was received."
    return _create(db, now, member_id, "payment_received", message)


def notify_fee_waived(db: Session, now: datetime.datetime, fee: Fee, waived_amount: Decimal) -> Notification:
    message = (
        f"Your {fee.kind.replace('_', ' ')} of {format_amount(fee.amount)} TRY was waived "
        f"(waived amount {format_amount(waived_amount)} TRY)."
    )
    return _create(db, now, fee.member_id, "fee_waived", message, loan_id=fee.loan_id, fee_id=fee.id)


# --- membership ------------------------------------------------------------------


def notify_membership_renewed(db: Session, now: datetime.datetime, member_id: int, valid_until: datetime.date) -> Notification:
    message = f"Your membership was renewed. It is valid until {valid_until.isoformat()}."
    return _create(db, now, member_id, "membership_renewed", message)


def notify_member_deactivated(db: Session, now: datetime.datetime, member_id: int) -> Notification:
    return _create(db, now, member_id, "member_deactivated", "Your membership was deactivated.")


# --- reminders (LIB-NOT-05, LIB-NOT-06) -------------------------------------------


def _already_sent(db: Session, type_: str, loan_id: int, reminder_date: datetime.date) -> bool:
    stmt = sa.select(Notification.id).where(
        Notification.type == type_, Notification.loan_id == loan_id, Notification.reminder_date == reminder_date
    )
    return db.scalar(stmt.limit(1)) is not None


def run_reminders(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date]
) -> tuple[int, int]:
    """Create today's ``due_reminder`` and ``overdue_notice`` notifications; returns the two counts."""
    today = now.date()
    next_day = add_working_days(today, 1, holidays)
    due_reminders = 0
    overdue_notices = 0

    due_loans = db.scalars(
        sa.select(Loan).where(Loan.status == "open", Loan.due_date == next_day).order_by(Loan.id)
    ).all()
    for loan in due_loans:
        if _already_sent(db, "due_reminder", loan.id, loan.due_date):
            continue
        title = _title_of_loan(db, loan)
        _create(
            db, now, loan.member_id, "due_reminder",
            f'Your loan of "{title}" is due on {loan.due_date.isoformat()}.',
            loan_id=loan.id, reminder_date=loan.due_date,
        )
        due_reminders += 1

    overdue_loans = db.scalars(
        sa.select(Loan).where(Loan.status == "open", Loan.due_date < today).order_by(Loan.id)
    ).all()
    for loan in overdue_loans:
        if _already_sent(db, "overdue_notice", loan.id, today):
            continue
        title = _title_of_loan(db, loan)
        _create(
            db, now, loan.member_id, "overdue_notice",
            f'Your loan of "{title}" was due on {loan.due_date.isoformat()} and is overdue.',
            loan_id=loan.id, reminder_date=today,
        )
        overdue_notices += 1

    record(
        db,
        at=now,
        event="reminders_run",
        actor_user_id=actor.id,
        entity_type="notification",
        entity_id=None,
        details={"due_reminders": due_reminders, "overdue_notices": overdue_notices},
    )
    return due_reminders, overdue_notices


# --- reading ---------------------------------------------------------------------


def mark_read(now: datetime.datetime, notification: Notification) -> Notification:
    """LIB-NOT-04: ``read_at`` is set once."""
    if notification.read_at is None:
        notification.read_at = now
    return notification


def mark_all_read(db: Session, now: datetime.datetime, member_id: int) -> int:
    result = db.execute(
        sa.update(Notification)
        .where(Notification.member_id == member_id, Notification.read_at.is_(None))
        .values(read_at=now)
    )
    return result.rowcount or 0


def unread_count(db: Session, member_id: int) -> int:
    stmt = sa.select(sa.func.count()).select_from(Notification).where(
        Notification.member_id == member_id, Notification.read_at.is_(None)
    )
    return db.scalar(stmt) or 0


def notification_list_stmt(
    *, member_id: int | None = None, unread: bool | None = None, type_: str | None = None
) -> sa.Select[tuple[Notification]]:
    """LIB-NOT-03: newest first."""
    stmt = sa.select(Notification).order_by(Notification.created_at.desc(), Notification.id.desc())
    if member_id is not None:
        stmt = stmt.where(Notification.member_id == member_id)
    if unread is not None:
        stmt = stmt.where(Notification.read_at.is_(None) if unread else Notification.read_at.is_not(None))
    if type_ is not None:
        stmt = stmt.where(Notification.type == type_)
    return stmt
