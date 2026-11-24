"""Lookups of module 21 used by other modules (members, branches) and the course reserves report (LIB-CRS-46).

Imports only models and the audit log, so that the other modules can use it without import cycles."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.catalog.models import Copy
from lms.core.clock import LOCAL_TZ
from lms.core.money import ZERO, format_amount
from lms.courses import accrual
from lms.courses.models import (
    OPEN_COURSE_STATUSES,
    Course,
    Enrollment,
    ReadingListItem,
    ReserveLoan,
)
from lms.courses.rules import LATE_GRACE_MINUTES
from lms.courses.schemas import CourseReportOut, CourseReservesSummaryOut
from lms.fines.models import Fee


def has_open_loan(db: Session, member_id: int) -> bool:
    """LIB-CRS-39: the member has an open reserve loan."""
    return accrual.count_open(db, member_id) > 0


def instructed_course_ids(db: Session, member_id: int) -> list[int]:
    """Ids of the ``draft`` and ``active`` courses the member teaches (LIB-CRS-39, LIB-CRS-40)."""
    stmt = (
        sa.select(Course.id)
        .where(Course.instructor_id == member_id, Course.status.in_(OPEN_COURSE_STATUSES))
        .order_by(Course.id)
    )
    return list(db.scalars(stmt))


def enrolled_course_ids(db: Session, member_id: int) -> list[int]:
    """Ids of the ``draft`` and ``active`` courses in which the member is ``enrolled``."""
    stmt = (
        sa.select(Course.id)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(
            Enrollment.member_id == member_id,
            Enrollment.status == "enrolled",
            Course.status.in_(OPEN_COURSE_STATUSES),
        )
        .order_by(Course.id)
    )
    return list(db.scalars(stmt))


def branch_has_open_courses(db: Session, branch_id: int) -> bool:
    """LIB-CRS-41."""
    stmt = sa.select(Course.id).where(Course.branch_id == branch_id, Course.status.in_(OPEN_COURSE_STATUSES)).limit(1)
    return db.scalar(stmt) is not None


def book_has_items(db: Session, book_id: int) -> bool:
    return db.scalar(sa.select(ReadingListItem.id).where(ReadingListItem.book_id == book_id).limit(1)) is not None


def drop_enrollment(
    db: Session, now: datetime.datetime, actor_user_id: int | None, enrollment: Enrollment, reason: str
) -> None:
    enrollment.status = "dropped"
    enrollment.dropped_at = now
    enrollment.drop_reason = reason
    record(
        db,
        at=now,
        event="course_enrollment_dropped",
        actor_user_id=actor_user_id,
        entity_type="course_enrollment",
        entity_id=enrollment.id,
        details={"course_id": enrollment.course_id, "member_id": enrollment.member_id, "reason": reason},
    )


def on_member_deactivated(db: Session, now: datetime.datetime, actor_user_id: int | None, member_id: int) -> None:
    """LIB-CRS-39: the member's ``enrolled`` enrollments are dropped with reason ``member_deactivated``."""
    enrollments = db.scalars(
        sa.select(Enrollment)
        .where(Enrollment.member_id == member_id, Enrollment.status == "enrolled")
        .order_by(Enrollment.id)
    ).all()
    for enrollment in enrollments:
        drop_enrollment(db, now, actor_user_id, enrollment, "member_deactivated")


def member_summary(db: Session, now: datetime.datetime, member_id: int) -> CourseReservesSummaryOut:
    """LIB-CRS-38."""
    return CourseReservesSummaryOut(
        courses_enrolled=len(enrolled_course_ids(db, member_id)),
        courses_teaching=len(instructed_course_ids(db, member_id)),
        open_reserve_loans=accrual.count_open(db, member_id),
        overdue_reserve_loans=accrual.count_overdue(db, member_id, now),
    )


# --- report (LIB-CRS-46) ---------------------------------------------------------------------


def report_courses(
    first: datetime.date, last: datetime.date, *, branch_id: int | None = None
) -> sa.Select[tuple[Course]]:
    stmt = (
        sa.select(Course)
        .where(Course.status != "draft", Course.starts_on <= last, Course.ends_on >= first)
        .order_by(Course.term, Course.code, Course.id)
    )
    if branch_id is not None:
        stmt = stmt.where(Course.branch_id == branch_id)
    return stmt


def report_out(db: Session, course: Course, first: datetime.date, last: datetime.date) -> CourseReportOut:
    enrolled = db.scalar(
        sa.select(sa.func.count()).select_from(Enrollment).where(
            Enrollment.course_id == course.id, Enrollment.status == "enrolled"
        )
    )
    items = db.scalars(
        sa.select(ReadingListItem).where(ReadingListItem.course_id == course.id, ReadingListItem.status != "removed")
    ).all()
    unfilled = 0
    for item in items:
        reserved = db.scalar(
            sa.select(sa.func.count()).select_from(Copy).where(
                Copy.reserve_item_id == item.id, Copy.status == "on_reserve"
            )
        )
        if (reserved or 0) < item.copies_wanted:
            unfilled += 1
    start = datetime.datetime.combine(first, datetime.time.min, LOCAL_TZ)
    end = datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time.min, LOCAL_TZ)
    loans = db.scalars(
        sa.select(ReserveLoan).where(
            ReserveLoan.course_id == course.id, ReserveLoan.lent_at >= start, ReserveLoan.lent_at < end
        )
    ).all()
    late_returns = sum(
        1 for ln in loans if ln.status == "returned" and ln.late_minutes is not None and ln.late_minutes > LATE_GRACE_MINUTES
    )
    charged: Decimal = ZERO
    if loans:
        fees = db.scalars(
            sa.select(Fee).where(Fee.reserve_loan_id.in_([ln.id for ln in loans]), Fee.status != "waived")
        )
        charged = sum((f.amount for f in fees), ZERO)
    return CourseReportOut(
        course_id=course.id,
        code=course.code,
        title=course.title,
        term=course.term,
        status=course.status,
        enrolled=enrolled or 0,
        items=len(items),
        items_unfilled=unfilled,
        loans=len(loans),
        borrowers=len({ln.member_id for ln in loans}),
        late_returns=late_returns,
        fees_charged=format_amount(charged),
    )
