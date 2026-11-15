"""Threads and messages: write, reply, assign, close, reopen and rate (sections 35.4 and 35.5)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.core.calendar import add_working_days
from lms.core.clock import LOCAL_TZ
from lms.core.errors import Conflict, NotFound, ValidationFailed, reference_not_found
from lms.core.money import format_amount
from lms.fines.models import Fee
from lms.loans.models import Loan
from lms.members.models import Member
from lms.messaging.models import Message, Thread
from lms.messaging.rules import (
    DAILY_MESSAGE_LIMIT,
    REOPEN_DAYS,
    RESPONSE_WORKING_DAYS,
    THREAD_LIMIT,
)
from lms.messaging.schemas import (
    ThreadFeeOut,
    ThreadLoanOut,
    ThreadMemberOut,
    ThreadOut,
    message_out,
    thread_out,
)
from lms.messaging.usage import close_thread
from lms.notifications.service import notify_message_reply


def get_thread_or_404(db: Session, thread_id: int) -> Thread:
    thread = db.get(Thread, thread_id)
    if thread is None:
        raise NotFound(f"Thread {thread_id} does not exist", details={"resource": "thread", "id": thread_id})
    return thread


def _closed_error(thread: Thread) -> Conflict:
    return Conflict("The thread is closed", code="THREAD_CLOSED", details={"id": thread.id})


def due_at_for(now: datetime.datetime, holidays: Container[datetime.date]) -> datetime.datetime:
    """LIB-MSG-23: the same time of day, 2 working days later."""
    day = add_working_days(now.date(), RESPONSE_WORKING_DAYS, holidays)
    return datetime.datetime.combine(day, now.timetz())


def _add_message(
    db: Session, now: datetime.datetime, thread: Thread, author: str, user_id: int | None, body: str, internal: bool
) -> Message:
    message = Message(
        thread_id=thread.id, author=author, user_id=user_id, body=body, internal=internal, created_at=now
    )
    db.add(message)
    db.flush()
    return message


def _message_audit(db: Session, now: datetime.datetime, actor_user_id: int | None, message: Message) -> None:
    record(
        db,
        at=now,
        event="thread_message_added",
        actor_user_id=actor_user_id,
        entity_type="thread",
        entity_id=message.thread_id,
        details={"message_id": message.id, "author": message.author, "internal": message.internal},
    )


# --- write --------------------------------------------------------------------------------------


def open_thread_count(db: Session, member_id: int) -> int:
    return (
        db.scalar(
            sa.select(sa.func.count()).select_from(Thread).where(Thread.member_id == member_id, Thread.status != "closed")
        )
        or 0
    )


def _limit_error() -> Conflict:
    return Conflict(
        "The member has too many threads that are not closed", code="THREAD_LIMIT_REACHED", details={"limit": THREAD_LIMIT}
    )


def create_thread(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    user: User,
    member: Member,
    data: dict[str, Any],
) -> Thread:
    """LIB-MSG-14, LIB-MSG-15 and LIB-MSG-20."""
    if data["loan_id"] is not None and data["category"] != "loan":
        raise ValidationFailed.single("loan_id", "loan_id needs the category loan")
    if data["fee_id"] is not None and data["category"] != "fee":
        raise ValidationFailed.single("fee_id", "fee_id needs the category fee")
    branch = db.get(Branch, data["branch_id"])
    if branch is None:
        raise reference_not_found("branch_id", data["branch_id"])
    loan = db.get(Loan, data["loan_id"]) if data["loan_id"] is not None else None
    if data["loan_id"] is not None and loan is None:
        raise reference_not_found("loan_id", data["loan_id"])
    fee = db.get(Fee, data["fee_id"]) if data["fee_id"] is not None else None
    if data["fee_id"] is not None and fee is None:
        raise reference_not_found("fee_id", data["fee_id"])

    if member.status == "passive":
        raise Conflict("The member is passive", code="MEMBER_PASSIVE")
    if not branch.is_active:
        raise Conflict(
            f"Branch {branch.code} is inactive",
            code="BRANCH_INACTIVE",
            details={"field": "branch_id", "id": branch.id},
        )
    if open_thread_count(db, member.id) >= THREAD_LIMIT:
        raise _limit_error()
    if loan is not None and loan.member_id != member.id:
        raise Conflict("The loan is not a loan of the member", code="NOT_OWN_RECORD", details={"field": "loan_id"})
    if fee is not None and fee.member_id != member.id:
        raise Conflict("The fee is not a fee of the member", code="NOT_OWN_RECORD", details={"field": "fee_id"})

    thread = Thread(
        member_id=member.id,
        branch_id=branch.id,
        subject=data["subject"],
        category=data["category"],
        loan_id=data["loan_id"],
        fee_id=data["fee_id"],
        status="open",
        due_at=due_at_for(now, holidays),
        created_at=now,
    )
    db.add(thread)
    db.flush()
    _add_message(db, now, thread, "member", user.id, data["body"], False)
    record(
        db,
        at=now,
        event="thread_created",
        actor_user_id=user.id,
        entity_type="thread",
        entity_id=thread.id,
        details={
            "member_id": member.id,
            "branch_id": branch.id,
            "subject": thread.subject,
            "category": thread.category,
            "loan_id": thread.loan_id,
            "fee_id": thread.fee_id,
        },
    )
    return thread


# --- reply --------------------------------------------------------------------------------------


def _member_messages_today(db: Session, now: datetime.datetime, thread_id: int) -> int:
    start = datetime.datetime.combine(now.date(), datetime.time.min, LOCAL_TZ)
    end = start + datetime.timedelta(days=1)
    return (
        db.scalar(
            sa.select(sa.func.count())
            .select_from(Message)
            .where(
                Message.thread_id == thread_id,
                Message.author == "member",
                Message.created_at >= start,
                Message.created_at < end,
            )
        )
        or 0
    )


def reply(
    db: Session,
    now: datetime.datetime,
    holidays: Container[datetime.date],
    user: User,
    thread: Thread,
    body: str,
    internal: bool,
) -> Message:
    """LIB-MSG-18, LIB-MSG-22, LIB-MSG-25 and LIB-MSG-45."""
    if thread.status == "closed":
        raise _closed_error(thread)
    if user.role == "member":
        if _member_messages_today(db, now, thread.id) >= DAILY_MESSAGE_LIMIT:
            raise Conflict(
                "Too many messages in this thread today",
                code="MESSAGE_LIMIT_REACHED",
                details={"limit": DAILY_MESSAGE_LIMIT},
            )
        message = _add_message(db, now, thread, "member", user.id, body, False)
        if thread.status == "answered":
            thread.status = "open"
            thread.due_at = due_at_for(now, holidays)
    else:
        message = _add_message(db, now, thread, "staff", user.id, body, internal)
        if not internal:
            thread.status = "answered"
            if thread.first_reply_at is None:
                thread.first_reply_at = now
            thread.due_at = None
            if thread.assigned_to is None:
                thread.assigned_to = user.id
            notify_message_reply(db, now, thread.member_id, thread.subject, thread_id=thread.id)
    _message_audit(db, now, user.id, message)
    return message


# --- assign, close, reopen, rate ----------------------------------------------------------------


def assign(db: Session, now: datetime.datetime, actor: User, thread: Thread, user_id: int | None) -> Thread:
    """LIB-MSG-24."""
    if user_id is not None:
        assignee = db.get(User, user_id)
        if assignee is None or not assignee.is_active or assignee.role not in ("librarian", "admin"):
            raise ValidationFailed.single("user_id", "user_id must be an active librarian or admin user")
    if thread.status == "closed":
        raise _closed_error(thread)
    old = thread.assigned_to
    thread.assigned_to = user_id
    record(
        db,
        at=now,
        event="thread_assigned",
        actor_user_id=actor.id,
        entity_type="thread",
        entity_id=thread.id,
        details={"assigned_to": {"old": old, "new": user_id}},
    )
    return thread


def close(db: Session, now: datetime.datetime, actor: User, thread: Thread) -> Thread:
    """LIB-MSG-26."""
    if thread.status == "closed":
        raise _closed_error(thread)
    close_thread(db, now, actor.id, thread, "member_request" if actor.role == "member" else "staff_request")
    return thread


def reopen(db: Session, now: datetime.datetime, holidays: Container[datetime.date], actor: User, thread: Thread) -> Thread:
    """LIB-MSG-27."""
    if thread.status != "closed":
        raise Conflict("The thread is not closed", code="THREAD_NOT_CLOSED", details={"status": thread.status})
    if (
        thread.close_reason not in ("member_request", "staff_request", "inactive")
        or thread.closed_at is None
        or now > thread.closed_at + datetime.timedelta(days=REOPEN_DAYS)
    ):
        raise Conflict(
            "The thread cannot be reopened",
            code="THREAD_REOPEN_NOT_ALLOWED",
            details={"close_reason": thread.close_reason},
        )
    if open_thread_count(db, thread.member_id) >= THREAD_LIMIT:
        raise _limit_error()
    thread.status = "open"
    thread.due_at = due_at_for(now, holidays)
    thread.close_reason = None
    thread.closed_at = None
    record(
        db,
        at=now,
        event="thread_reopened",
        actor_user_id=actor.id,
        entity_type="thread",
        entity_id=thread.id,
        details={"member_id": thread.member_id},
    )
    return thread


def rate(db: Session, now: datetime.datetime, actor: User, thread: Thread, rating: int) -> Thread:
    """LIB-MSG-30."""
    if thread.status != "closed":
        raise Conflict("The thread is not closed", code="THREAD_NOT_CLOSED", details={"status": thread.status})
    if thread.rating is not None:
        raise Conflict("The thread is already rated", code="ALREADY_RATED", details={"rating": thread.rating})
    replied = db.scalar(
        sa.select(Message.id)
        .where(Message.thread_id == thread.id, Message.author == "staff", Message.internal.is_(False))
        .limit(1)
    )
    if replied is None:
        raise Conflict("The thread has no staff reply to rate", code="NOTHING_TO_RATE")
    thread.rating = rating
    record(
        db,
        at=now,
        event="thread_rated",
        actor_user_id=actor.id,
        entity_type="thread",
        entity_id=thread.id,
        details={"rating": rating},
    )
    return thread


# --- reading ------------------------------------------------------------------------------------


def _visible(staff: bool) -> list[Any]:
    """Internal notes are never visible to members."""
    return [] if staff else [Message.internal.is_(False)]


def list_stmt(
    now: datetime.datetime,
    *,
    staff: bool,
    member_id: int | None = None,
    status: str | None = None,
    branch_id: int | None = None,
    assigned_to: int | None = None,
    category: str | None = None,
    overdue: bool | None = None,
) -> sa.Select[tuple[Thread]]:
    """LIB-MSG-16: newest last message first, then ``id`` descending."""
    last = (
        sa.select(sa.func.max(Message.created_at))
        .where(Message.thread_id == Thread.id, *_visible(staff))
        .correlate(Thread)
        .scalar_subquery()
    )
    stmt = sa.select(Thread).order_by(sa.func.coalesce(last, Thread.created_at).desc(), Thread.id.desc())
    if member_id is not None:
        stmt = stmt.where(Thread.member_id == member_id)
    if status is not None:
        stmt = stmt.where(Thread.status == status)
    if branch_id is not None:
        stmt = stmt.where(Thread.branch_id == branch_id)
    if assigned_to is not None:
        stmt = stmt.where(Thread.assigned_to == assigned_to)
    if category is not None:
        stmt = stmt.where(Thread.category == category)
    if overdue is not None:
        is_overdue = sa.and_(Thread.status == "open", Thread.due_at.is_not(None), Thread.due_at < now)
        stmt = stmt.where(is_overdue if overdue else sa.not_(is_overdue))
    return stmt


def _last_message_at(db: Session, thread_id: int, staff: bool) -> datetime.datetime | None:
    return db.scalar(
        sa.select(sa.func.max(Message.created_at)).where(Message.thread_id == thread_id, *_visible(staff))
    )


def _unread(db: Session, thread_id: int, staff: bool) -> int:
    """Messages of the other side without ``read_at``; internal notes never count."""
    stmt = sa.select(sa.func.count()).select_from(Message).where(
        Message.thread_id == thread_id,
        Message.author == ("member" if staff else "staff"),
        Message.internal.is_(False),
        Message.read_at.is_(None),
    )
    return db.scalar(stmt) or 0


def mark_read(db: Session, now: datetime.datetime, thread: Thread, staff: bool) -> None:
    """LIB-MSG-17: the other side's messages are read."""
    db.execute(
        sa.update(Message)
        .where(
            Message.thread_id == thread.id,
            Message.author == ("member" if staff else "staff"),
            Message.internal.is_(False),
            Message.read_at.is_(None),
        )
        .values(read_at=now)
    )
    db.flush()


def to_out(db: Session, now: datetime.datetime, thread: Thread, *, staff: bool, with_messages: bool = False) -> ThreadOut:
    """LIB-MSG-16, LIB-MSG-17, LIB-MSG-21 and LIB-MSG-31."""
    result = thread_out(
        thread,
        last_message_at=_last_message_at(db, thread.id, staff) or thread.created_at,
        unread=_unread(db, thread.id, staff),
        now=now,
    )
    if staff:
        member = db.get(Member, thread.member_id)
        if member is not None:
            result.member = ThreadMemberOut(
                id=member.id,
                member_no=member.member_no,
                full_name=member.full_name,
                membership_type=member.membership_type,
            )
        loan = db.get(Loan, thread.loan_id) if thread.loan_id is not None else None
        if loan is not None:
            result.loan = ThreadLoanOut(id=loan.id, status=loan.status, due_date=loan.due_date)
        fee = db.get(Fee, thread.fee_id) if thread.fee_id is not None else None
        if fee is not None:
            result.fee = ThreadFeeOut(id=fee.id, kind=fee.kind, amount=format_amount(fee.amount), status=fee.status)
    if with_messages:
        messages = db.scalars(
            sa.select(Message).where(Message.thread_id == thread.id, *_visible(staff)).order_by(Message.created_at, Message.id)
        ).all()
        result.messages = [message_out(m) for m in messages]
    return result
