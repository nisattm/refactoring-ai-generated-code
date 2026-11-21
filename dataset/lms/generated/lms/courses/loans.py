"""Reserve loans (LIB-CRS-24 to LIB-CRS-33)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.branches.models import Branch
from lms.catalog.models import Book, Copy
from lms.catalog.status import set_status
from lms.core.errors import Conflict, NotFound, reference_not_found
from lms.core.lookup import get_or_404
from lms.core.money import format_amount
from lms.core.timeutil import format_datetime
from lms.courses import accrual
from lms.courses.courses import is_enrolled
from lms.courses.models import Course, ReadingListItem, ReserveLoan
from lms.courses.reserve import refresh_item_status
from lms.courses.rules import (
    DEBT_BLOCK,
    RESERVE_LOAN_LIMITS,
    due_at_for,
    late_fee_amount,
    late_minutes_between,
)
from lms.courses.schemas import ReserveLoanOut
from lms.equipment.rules import desk_open
from lms.fines import service as fines
from lms.loans.models import Loan
from lms.members.models import Member
from lms.staff.schedule import load_schedule


def _error(code: str, message: str, **details: Any) -> Conflict:
    return Conflict(message, code=code, details=details)


def get_loan_or_404(db: Session, loan_id: int) -> ReserveLoan:
    return get_or_404(db, ReserveLoan, loan_id, "Reserve loan", "reserve_loan")


def to_out(db: Session, loan: ReserveLoan, now: datetime.datetime) -> ReserveLoanOut:
    title = (
        db.scalar(
            sa.select(Book.title)
            .join(ReadingListItem, ReadingListItem.book_id == Book.id)
            .where(ReadingListItem.id == loan.item_id)
        )
        or ""
    )
    code = db.scalar(sa.select(Course.code).where(Course.id == loan.course_id)) or ""
    return ReserveLoanOut(
        id=loan.id,
        copy_id=loan.copy_id,
        item_id=loan.item_id,
        course_id=loan.course_id,
        member_id=loan.member_id,
        lent_at=format_datetime(loan.lent_at),
        due_at=format_datetime(loan.due_at),
        renewed=loan.renewed,
        status=loan.status,
        returned_at=format_datetime(loan.returned_at) if loan.returned_at is not None else None,
        late_minutes=loan.late_minutes,
        fee_id=loan.fee_id,
        book_title=title,
        course_code=code,
        is_overdue=accrual.is_overdue(loan, now),
        accrued_late_fee=format_amount(accrual.accrued_late_fee(loan, now)),
    )


# --- LIB-CRS-24 ---------------------------------------------------------------------------------


def _find_copy(db: Session, copy_id: int | None, barcode: str | None) -> Copy:
    if copy_id is not None:
        copy = db.get(Copy, copy_id)
        if copy is None:
            raise reference_not_found("copy_id", copy_id)
        return copy
    assert barcode is not None
    copy = db.scalar(sa.select(Copy).where(Copy.barcode == barcode.upper()))
    if copy is None:
        raise NotFound(f"No copy has barcode {barcode}", details={"field": "barcode", "value": barcode})
    return copy


def _has_overdue_book_loan(db: Session, member_id: int, today: datetime.date) -> bool:
    stmt = sa.select(Loan.id).where(Loan.member_id == member_id, Loan.status == "open", Loan.due_date < today)
    return db.scalar(stmt.limit(1)) is not None


def lend(
    db: Session,
    now: datetime.datetime,
    actor: User,
    holidays: Container[datetime.date],
    *,
    member_id: int,
    copy_id: int | None,
    barcode: str | None,
) -> ReserveLoan:
    member = db.get(Member, member_id)
    if member is None:
        raise reference_not_found("member_id", member_id)
    copy = _find_copy(db, copy_id, barcode)

    if copy.status != "on_reserve":
        raise _error("COPY_NOT_ON_RESERVE", f"The copy has status {copy.status}", status=copy.status)
    course = db.get(Course, copy.reserve_course_id)
    item = db.get(ReadingListItem, copy.reserve_item_id)
    assert course is not None and item is not None
    today = now.date()
    if not course.is_running_on(today):
        raise _error("COURSE_NOT_RUNNING", "The course is not running today", status=course.status)
    schedule = load_schedule(db, course.branch_id)
    if not desk_open(now, holidays, schedule):
        raise _error("RESERVE_DESK_CLOSED", "The reserve desk is closed", branch_id=course.branch_id)
    if member.status == "passive":
        raise _error("MEMBER_PASSIVE", "The member is passive")
    if today > member.valid_until:
        raise _error("MEMBERSHIP_EXPIRED", "The membership has expired")
    if member.id != course.instructor_id and not is_enrolled(db, course.id, member.id):
        raise _error("NOT_ENROLLED", "The member is not enrolled in the course and does not teach it")
    if _has_overdue_book_loan(db, member.id, today) or accrual.count_overdue(db, member.id, now) > 0:
        raise _error("MEMBER_HAS_OVERDUE", "The member has an overdue loan")
    debt = fines.outstanding_fees(db, member.id) + fines.accrued_late_fees(db, member.id, now, holidays)
    if debt >= DEBT_BLOCK:
        raise _error("MEMBER_BLOCKED_BY_DEBT", "The member's debt is too high", total_debt=format_amount(debt))
    same_item = sa.select(ReserveLoan.id).where(
        ReserveLoan.member_id == member.id, ReserveLoan.item_id == item.id, ReserveLoan.status == "open"
    )
    if db.scalar(same_item.limit(1)) is not None:
        raise _error("ALREADY_BORROWED", "The member already borrows a copy of this item", item_id=item.id)
    limit = RESERVE_LOAN_LIMITS[member.membership_type]
    if accrual.count_open(db, member.id) >= limit:
        raise _error("RESERVE_LOAN_LIMIT_REACHED", "The reserve loan limit is reached", limit=limit)
    current = db.scalar(sa.select(ReserveLoan).where(ReserveLoan.copy_id == copy.id, ReserveLoan.status == "open"))
    if current is not None:
        raise _error(
            "COPY_ON_RESERVE_LOAN", "The copy is on a reserve loan", due_at=_iso(current.due_at)
        )

    loan = ReserveLoan(
        copy_id=copy.id,
        item_id=item.id,
        course_id=course.id,
        member_id=member.id,
        lent_at=now,
        due_at=due_at_for(now, item.loan_period, schedule, holidays),
        loan_period=item.loan_period,
        renewed=False,
        status="open",
        created_by=actor.id,
    )
    db.add(loan)
    db.flush()
    record(
        db,
        at=now,
        event="reserve_loan_created",
        actor_user_id=actor.id,
        entity_type="reserve_loan",
        entity_id=loan.id,
        details={
            "member_id": member.id,
            "copy_id": copy.id,
            "item_id": item.id,
            "course_id": course.id,
            "due_at": _iso(loan.due_at),
        },
    )
    return loan


def _iso(value: datetime.datetime) -> str:
    return format_datetime(value)


# --- LIB-CRS-27 ---------------------------------------------------------------------------------


def renew(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date], loan: ReserveLoan
) -> ReserveLoan:
    if loan.status != "open":
        raise _error("RESERVE_LOAN_NOT_OPEN", "The reserve loan is not open", status=loan.status)
    if loan.renewed:
        raise _error("RENEWAL_LIMIT_REACHED", "The reserve loan was renewed already")
    if accrual.is_overdue(loan, now):
        raise _error("LOAN_OVERDUE", "The reserve loan is overdue", due_at=_iso(loan.due_at))
    course = db.get(Course, loan.course_id)
    assert course is not None
    if not course.is_running_on(now.date()):
        raise _error("COURSE_NOT_RUNNING", "The course is not running today", status=course.status)
    on_loan = sa.select(ReserveLoan.id).where(ReserveLoan.copy_id == Copy.id, ReserveLoan.status == "open")
    other = db.scalar(
        sa.select(Copy.id)
        .where(
            Copy.reserve_item_id == loan.item_id,
            Copy.status == "on_reserve",
            Copy.id != loan.copy_id,
            ~on_loan.exists(),
        )
        .limit(1)
    )
    if other is None:
        raise _error("RESERVE_IN_DEMAND", "No other copy of the item is free", item_id=loan.item_id)
    old_due = loan.due_at
    loan.due_at = due_at_for(now, loan.loan_period, load_schedule(db, course.branch_id), holidays)
    loan.renewed = True
    record(
        db,
        at=now,
        event="reserve_loan_renewed",
        actor_user_id=actor.id,
        entity_type="reserve_loan",
        entity_id=loan.id,
        details={"member_id": loan.member_id, "due_at": {"old": _iso(old_due), "new": _iso(loan.due_at)}},
    )
    return loan


# --- LIB-CRS-28, LIB-CRS-29 ---------------------------------------------------------------------


def _late_fee(db: Session, now: datetime.datetime, actor: User, loan: ReserveLoan) -> None:
    amount = late_fee_amount(loan.loan_period, loan.late_minutes or 0)
    if amount > 0:
        fee = fines.create_fee(
            db, now, actor, member_id=loan.member_id, loan_id=None, kind="reserve_late_fee", amount=amount,
            reserve_loan_id=loan.id,
        )
        loan.fee_id = fee.id


def return_loan(
    db: Session, now: datetime.datetime, actor: User, loan: ReserveLoan, branch_id: int
) -> ReserveLoan:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise reference_not_found("branch_id", branch_id)
    if loan.status != "open":
        raise _error("RESERVE_LOAN_NOT_OPEN", "The reserve loan is not open", status=loan.status)
    course = db.get(Course, loan.course_id)
    assert course is not None
    if branch_id != course.branch_id:
        raise _error(
            "RESERVE_RETURN_WRONG_BRANCH", "The copy belongs to the reserve desk of another branch", branch_id=course.branch_id
        )
    loan.status = "returned"
    loan.returned_at = now
    loan.late_minutes = late_minutes_between(loan.due_at, now)
    record(
        db,
        at=now,
        event="reserve_loan_returned",
        actor_user_id=actor.id,
        entity_type="reserve_loan",
        entity_id=loan.id,
        details={"member_id": loan.member_id, "copy_id": loan.copy_id, "late_minutes": loan.late_minutes},
    )
    _late_fee(db, now, actor, loan)
    return loan


# --- LIB-CRS-31 ---------------------------------------------------------------------------------


def report_lost(db: Session, now: datetime.datetime, actor: User, loan: ReserveLoan) -> ReserveLoan:
    if loan.status != "open":
        raise _error("RESERVE_LOAN_NOT_OPEN", "The reserve loan is not open", status=loan.status)
    copy = db.get(Copy, loan.copy_id)
    assert copy is not None
    loan.status = "lost"
    loan.late_minutes = late_minutes_between(loan.due_at, now)
    item = db.get(ReadingListItem, loan.item_id)
    set_status(copy, "lost")
    copy.current_branch_id = None
    copy.reserve_item_id = None
    copy.reserve_course_id = None
    db.flush()
    if item is not None:
        refresh_item_status(db, item)
    record(
        db,
        at=now,
        event="reserve_loan_lost",
        actor_user_id=actor.id,
        entity_type="reserve_loan",
        entity_id=loan.id,
        details={"member_id": loan.member_id, "copy_id": loan.copy_id, "late_minutes": loan.late_minutes},
    )
    _late_fee(db, now, actor, loan)
    fines.create_fee(
        db, now, actor, member_id=loan.member_id, loan_id=None, kind="reserve_lost", amount=copy.price,
        reserve_loan_id=loan.id,
    )
    return loan


# --- LIB-CRS-32 ---------------------------------------------------------------------------------


def loan_list_stmt(
    now: datetime.datetime,
    *,
    course_id: int | None = None,
    member_id: int | None = None,
    status: str | None = None,
    overdue: bool | None = None,
) -> sa.Select[tuple[ReserveLoan]]:
    stmt = sa.select(ReserveLoan).order_by(ReserveLoan.id.desc())
    if course_id is not None:
        stmt = stmt.where(ReserveLoan.course_id == course_id)
    if member_id is not None:
        stmt = stmt.where(ReserveLoan.member_id == member_id)
    if status is not None:
        stmt = stmt.where(ReserveLoan.status == status)
    if overdue is not None:
        is_overdue = sa.and_(ReserveLoan.status == "open", ReserveLoan.due_at < now)
        stmt = stmt.where(is_overdue if overdue else sa.not_(is_overdue))
    return stmt
