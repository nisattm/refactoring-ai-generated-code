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
from lms.core.lookup import get_or_404
from lms.core.money import format_amount
from lms.fines.models import Fee
from lms.loans.models import Loan
from lms.notifications.models import Notification
from lms.reservations.models import Reservation


def get_notification_or_404(db: Session, notification_id: int) -> Notification:
    return get_or_404(db, Notification, notification_id, "Notification", "notification")


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
    room_booking_id: int | None = None,
    equipment_loan_id: int | None = None,
    equipment_reservation_id: int | None = None,
    digital_loan_id: int | None = None,
    digital_hold_id: int | None = None,
    ill_request_id: int | None = None,
    event_id: int | None = None,
    event_registration_id: int | None = None,
    course_id: int | None = None,
    reserve_loan_id: int | None = None,
    donation_id: int | None = None,
    suggestion_id: int | None = None,
    program_id: int | None = None,
    announcement_id: int | None = None,
    thread_id: int | None = None,
    card_id: int | None = None,
    print_job_id: int | None = None,
    reminder_date: datetime.date | None = None,
) -> Notification:
    notification = Notification(
        member_id=member_id,
        type=type_,
        message=message,
        loan_id=loan_id,
        reservation_id=reservation_id,
        fee_id=fee_id,
        room_booking_id=room_booking_id,
        equipment_loan_id=equipment_loan_id,
        equipment_reservation_id=equipment_reservation_id,
        digital_loan_id=digital_loan_id,
        digital_hold_id=digital_hold_id,
        ill_request_id=ill_request_id,
        event_id=event_id,
        event_registration_id=event_registration_id,
        course_id=course_id,
        reserve_loan_id=reserve_loan_id,
        donation_id=donation_id,
        suggestion_id=suggestion_id,
        program_id=program_id,
        announcement_id=announcement_id,
        thread_id=thread_id,
        card_id=card_id,
        print_job_id=print_job_id,
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
    """``reservation_ready``, ``reservation_in_transit``, ``reservation_expired``, ``reservation_cancelled`` and
    ``reservation_delayed``."""
    title = _title_of_book(db, reservation.book_id)
    hold = reservation.hold_until.isoformat() if reservation.hold_until is not None else None
    if type_ == "reservation_ready":
        message = f'Your reservation of "{title}" is ready for pickup until {hold}.'
    elif type_ == "reservation_in_transit":
        message = f'A copy of "{title}" is on its way to your pickup branch.'
    elif type_ == "reservation_expired":
        message = f'Your reservation of "{title}" expired because it was not collected by {hold}.'
    elif type_ == "reservation_delayed":  # LIB-INV-20
        message = f'Your reservation of "{title}" is delayed: the copy held for you could not be found.'
    else:
        reason = reservation.cancel_reason
        message = f'Your reservation of "{title}" was cancelled ({reason}).'
        if hold is not None:
            message += f" The hold ran until {hold}."
    return _create(db, now, reservation.member_id, type_, message, reservation_id=reservation.id)


# --- fees and payments -----------------------------------------------------------


def notify_fee_created(db: Session, now: datetime.datetime, fee: Fee) -> Notification:
    message = f"A {fee.kind.replace('_', ' ')} of {format_amount(fee.amount)} TRY was added to your account."
    return _create(
        db, now, fee.member_id, "fee_created", message,
        loan_id=fee.loan_id, fee_id=fee.id, equipment_loan_id=fee.equipment_loan_id,
        ill_request_id=fee.ill_request_id, card_id=fee.card_id,
    )


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


# --- study rooms (LIB-ROOM-41, LIB-ROOM-42) ---------------------------------------


def notify_room(
    db: Session,
    now: datetime.datetime,
    member_id: int,
    type_: str,
    message: str,
    *,
    room_booking_id: int | None = None,
) -> Notification:
    """``room_booking_cancelled``, ``room_no_show``, ``room_ban_started``, ``room_participant_added``
    and ``room_reminder``; the caller composes the message."""
    return _create(db, now, member_id, type_, message, room_booking_id=room_booking_id)


def room_reminder_sent(db: Session, room_booking_id: int, member_id: int) -> bool:
    stmt = sa.select(Notification.id).where(
        Notification.type == "room_reminder",
        Notification.room_booking_id == room_booking_id,
        Notification.member_id == member_id,
    )
    return db.scalar(stmt.limit(1)) is not None


# --- equipment (LIB-EQ-32, LIB-EQ-38) ---------------------------------------------


def notify_equipment(
    db: Session,
    now: datetime.datetime,
    member_id: int,
    type_: str,
    message: str,
    *,
    equipment_loan_id: int | None = None,
    equipment_reservation_id: int | None = None,
    reminder_date: datetime.date | None = None,
) -> Notification:
    """``equipment_loan_created``, ``equipment_loan_returned``, ``equipment_loan_lost``,
    ``equipment_reservation_cancelled``, ``equipment_reservation_expired`` and ``equipment_overdue``;
    the caller composes the message."""
    return _create(
        db,
        now,
        member_id,
        type_,
        message,
        equipment_loan_id=equipment_loan_id,
        equipment_reservation_id=equipment_reservation_id,
        reminder_date=reminder_date,
    )


def equipment_overdue_notice_sent(db: Session, equipment_loan_id: int, day: datetime.date) -> bool:
    stmt = sa.select(Notification.id).where(
        Notification.type == "equipment_overdue",
        Notification.equipment_loan_id == equipment_loan_id,
        Notification.reminder_date == day,
    )
    return db.scalar(stmt.limit(1)) is not None


# --- digital resources (LIB-DIG-33, LIB-DIG-34) -----------------------------------


def notify_digital(
    db: Session,
    now: datetime.datetime,
    member_id: int,
    type_: str,
    message: str,
    *,
    digital_loan_id: int | None = None,
    digital_hold_id: int | None = None,
) -> Notification:
    """``digital_hold_ready``, ``digital_hold_expired``, ``digital_hold_cancelled``, ``digital_loan_expired``
    and ``digital_loan_due_soon``; the caller composes the message."""
    return _create(
        db, now, member_id, type_, message, digital_loan_id=digital_loan_id, digital_hold_id=digital_hold_id
    )


def digital_due_soon_sent(db: Session, digital_loan_id: int) -> bool:
    stmt = sa.select(Notification.id).where(
        Notification.type == "digital_loan_due_soon", Notification.digital_loan_id == digital_loan_id
    )
    return db.scalar(stmt.limit(1)) is not None


# --- interlibrary loans (LIB-ILL-36) ---------------------------------------------


def notify_ill(
    db: Session, now: datetime.datetime, member_id: int, type_: str, message: str, *, ill_request_id: int
) -> Notification:
    """``ill_request_rejected``, ``ill_request_cancelled``, ``ill_request_received``, ``ill_request_uncollected``
    and ``ill_renewal_answered``; the caller composes the message."""
    return _create(db, now, member_id, type_, message, ill_request_id=ill_request_id)


# --- events (LIB-EVT-44) ---------------------------------------------------------


def notify_event(
    db: Session,
    now: datetime.datetime,
    member_id: int,
    type_: str,
    message: str,
    *,
    event_id: int | None = None,
    event_registration_id: int | None = None,
) -> Notification:
    """``event_cancelled``, ``event_changed``, ``event_promoted``, ``event_reminder`` and ``event_ban_started``;
    the caller composes the message."""
    return _create(
        db, now, member_id, type_, message, event_id=event_id, event_registration_id=event_registration_id
    )


def event_reminder_sent(db: Session, event_registration_id: int) -> bool:
    stmt = sa.select(Notification.id).where(
        Notification.type == "event_reminder", Notification.event_registration_id == event_registration_id
    )
    return db.scalar(stmt.limit(1)) is not None


# --- course reserves (LIB-CRS-44) ------------------------------------------------


def notify_course(
    db: Session,
    now: datetime.datetime,
    member_id: int,
    type_: str,
    message: str,
    *,
    course_id: int,
    reserve_loan_id: int | None = None,
) -> Notification:
    """``course_enrolled``, ``course_activated``, ``reserve_item_available`` and ``reserve_overdue``;
    the caller composes the message."""
    return _create(db, now, member_id, type_, message, course_id=course_id, reserve_loan_id=reserve_loan_id)


def reserve_overdue_notice_sent(db: Session, reserve_loan_id: int) -> bool:
    stmt = sa.select(Notification.id).where(
        Notification.type == "reserve_overdue", Notification.reserve_loan_id == reserve_loan_id
    )
    return db.scalar(stmt.limit(1)) is not None


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


# --- donations (LIB-DON-41) ----------------------------------------------------------


def notify_donation(
    db: Session, now: datetime.datetime, member_id: int, type_: str, message: str, *, donation_id: int
) -> Notification:
    """``donation_reviewed``, ``donation_received``, ``donation_expired`` and ``donor_level_reached``;
    the caller composes the message."""
    return _create(db, now, member_id, type_, message, donation_id=donation_id)


# --- purchase suggestions (LIB-SUG-42) -----------------------------------------------


def notify_suggestion(
    db: Session, now: datetime.datetime, member_id: int, type_: str, message: str, *, suggestion_id: int
) -> Notification:
    """``suggestion_approved``, ``suggestion_rejected``, ``suggestion_ordered``, ``suggestion_available`` and
    ``suggestion_expired``."""
    return _create(db, now, member_id, type_, message, suggestion_id=suggestion_id)


# --- reading programs (LIB-RDP-42) ---------------------------------------------------


def notify_program(
    db: Session, now: datetime.datetime, member_id: int, type_: str, message: str, *, program_id: int
) -> Notification:
    """``program_completed``, ``program_level_reached``, ``program_cancelled`` and ``program_ending``; the caller
    composes the message, which contains the program name."""
    return _create(db, now, member_id, type_, message, program_id=program_id)



# --- announcements and messages (LIB-MSG-37) -----------------------------------------


def notify_announcement(
    db: Session, now: datetime.datetime, member_id: int, title: str, *, announcement_id: int
) -> Notification:
    """``announcement`` for an important announcement that became live (LIB-MSG-06)."""
    return _create(
        db, now, member_id, "announcement", f'New important announcement: "{title}".', announcement_id=announcement_id
    )


def notify_message_reply(
    db: Session, now: datetime.datetime, member_id: int, subject: str, *, thread_id: int
) -> Notification:
    """``message_reply`` for a staff reply that is not an internal note (LIB-MSG-18)."""
    return _create(
        db, now, member_id, "message_reply", f'The library replied to your message "{subject}".', thread_id=thread_id
    )


# --- member cards and building access (LIB-ACC-42) -----------------------------------


def notify_access(
    db: Session, now: datetime.datetime, member_id: int, type_: str, message: str, *, card_id: int | None = None
) -> Notification:
    """``card_issued``, ``access_banned`` and ``lost_card_used``; the caller composes the message, which
    contains the card number or the end date of the ban."""
    return _create(db, now, member_id, type_, message, card_id=card_id)


# --- printing and copying (LIB-PRT-42) -----------------------------------------------


def notify_printing(
    db: Session, now: datetime.datetime, member_id: int, type_: str, message: str, *, print_job_id: int
) -> Notification:
    """``print_job_cancelled``, ``print_job_expired`` and ``print_job_failed``; the caller composes the message,
    which contains the job title."""
    return _create(db, now, member_id, type_, message, print_job_id=print_job_id)
