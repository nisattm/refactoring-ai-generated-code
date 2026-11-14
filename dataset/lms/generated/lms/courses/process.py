"""Overdue notices and end of courses (LIB-CRS-33)."""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.catalog.models import Book
from lms.core.timeutil import format_datetime
from lms.courses.courses import finish_close, open_loan_ids
from lms.courses.models import Course, ReadingListItem, ReserveLoan
from lms.courses.schemas import ProcessOut
from lms.notifications.service import notify_course, reserve_overdue_notice_sent


def process(db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date]) -> ProcessOut:
    notices = 0
    overdue = db.scalars(
        sa.select(ReserveLoan)
        .where(ReserveLoan.status == "open", ReserveLoan.due_at < now)
        .order_by(ReserveLoan.due_at, ReserveLoan.id)
    ).all()
    for loan in overdue:
        if reserve_overdue_notice_sent(db, loan.id):
            continue
        code = db.scalar(sa.select(Course.code).where(Course.id == loan.course_id)) or ""
        title = (
            db.scalar(
                sa.select(Book.title)
                .join(ReadingListItem, ReadingListItem.book_id == Book.id)
                .where(ReadingListItem.id == loan.item_id)
            )
            or ""
        )
        notify_course(
            db,
            now,
            loan.member_id,
            "reserve_overdue",
            f'Your reserve loan of "{title}" for {code} was due at {format_datetime(loan.due_at)} and is overdue.',
            course_id=loan.course_id,
            reserve_loan_id=loan.id,
        )
        notices += 1

    closed = released = pending = 0
    ended = db.scalars(
        sa.select(Course).where(Course.status == "active", Course.ends_on < now.date()).order_by(Course.id)
    ).all()
    for course in ended:
        if open_loan_ids(db, course.id):
            pending += 1
            continue
        released += finish_close(db, now, actor, holidays, course)
        closed += 1

    record(
        db,
        at=now,
        event="course_reserves_processed",
        actor_user_id=actor.id,
        entity_type="course",
        entity_id=None,
        details={
            "overdue_notices": notices,
            "closed_courses": closed,
            "released_copies": released,
            "pending_courses": pending,
        },
    )
    return ProcessOut(overdue_notices=notices, closed_courses=closed, released_copies=released, pending_courses=pending)
