"""Placing copies on reserve (LIB-CRS-13, LIB-CRS-19, LIB-CRS-22) and the counts of 29.1.

Imports no module that depends on the reservation module, so that the release procedure (LIB-RES-08) can use it.
"""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.catalog.models import Book, Copy
from lms.courses.models import (
    OPEN_COURSE_STATUSES,
    Course,
    Enrollment,
    ReadingListItem,
    ReserveLoan,
)
from lms.notifications.service import notify_course


def copies_on_reserve_of_item(db: Session, item_id: int) -> list[Copy]:
    stmt = sa.select(Copy).where(Copy.reserve_item_id == item_id, Copy.status == "on_reserve").order_by(Copy.id)
    return list(db.scalars(stmt))


def count_reserved(db: Session, item_id: int) -> int:
    stmt = sa.select(sa.func.count()).select_from(Copy).where(Copy.reserve_item_id == item_id, Copy.status == "on_reserve")
    return db.scalar(stmt) or 0


def count_reserved_for_course(db: Session, course_id: int) -> int:
    stmt = sa.select(sa.func.count()).select_from(Copy).where(
        Copy.reserve_course_id == course_id, Copy.status == "on_reserve"
    )
    return db.scalar(stmt) or 0


def open_loan_ids(db: Session, *conditions: sa.ColumnElement[bool]) -> list[int]:
    stmt = sa.select(ReserveLoan.id).where(ReserveLoan.status == "open", *conditions).order_by(ReserveLoan.id)
    return list(db.scalars(stmt))


def enrolled_member_ids(db: Session, course_id: int) -> list[int]:
    stmt = (
        sa.select(Enrollment.member_id)
        .where(Enrollment.course_id == course_id, Enrollment.status == "enrolled")
        .order_by(Enrollment.id)
    )
    return list(db.scalars(stmt))


def place_copy(
    db: Session,
    now: datetime.datetime,
    actor_user_id: int | None,
    copy: Copy,
    item: ReadingListItem,
    course: Course,
) -> None:
    """The effects of LIB-CRS-19: the copy and the item become ``on_reserve``; the enrolled members of an ``active``
    course are told when the item gets its first copy."""
    copy.status = "on_reserve"
    copy.reserve_item_id = item.id
    copy.reserve_course_id = course.id
    first = item.status == "requested"
    item.status = "on_reserve"
    db.flush()
    record(
        db,
        at=now,
        event="reserve_copy_placed",
        actor_user_id=actor_user_id,
        entity_type="copy",
        entity_id=copy.id,
        details={"item_id": item.id, "course_id": course.id, "book_id": copy.book_id},
    )
    if first and course.status == "active":
        title = db.scalar(sa.select(Book.title).where(Book.id == item.book_id)) or f"book {item.book_id}"
        for member_id in enrolled_member_ids(db, course.id):
            notify_course(
                db,
                now,
                member_id,
                "reserve_item_available",
                f'"{title}" is now available on reserve for {course.code}.',
                course_id=course.id,
            )


def place_available_copies(
    db: Session, now: datetime.datetime, actor_user_id: int | None, item: ReadingListItem, course: Course
) -> None:
    """LIB-CRS-13: ``available`` copies of the book at the course's branch, in order of ``id``, up to ``copies_wanted``."""
    candidates = db.scalars(
        sa.select(Copy)
        .where(Copy.book_id == item.book_id, Copy.status == "available", Copy.current_branch_id == course.branch_id)
        .order_by(Copy.id)
    ).all()
    reserved = count_reserved(db, item.id)
    for copy in candidates:
        if reserved >= item.copies_wanted:
            break
        place_copy(db, now, actor_user_id, copy, item, course)
        reserved += 1


def place_on_release(db: Session, copy: Copy, now: datetime.datetime, actor_user_id: int | None) -> bool:
    """LIB-CRS-22: a copy that became free goes on reserve for the earliest ``required`` item of a ``draft`` or
    ``active`` course at the copy's branch that still wants copies. Returns whether the copy was placed."""
    if copy.current_branch_id is None:
        return False
    rows = db.execute(
        sa.select(ReadingListItem, Course)
        .join(Course, Course.id == ReadingListItem.course_id)
        .where(
            Course.branch_id == copy.current_branch_id,
            Course.status.in_(OPEN_COURSE_STATUSES),
            ReadingListItem.book_id == copy.book_id,
            ReadingListItem.kind == "required",
            ReadingListItem.status != "removed",
        )
        .order_by(ReadingListItem.added_at, ReadingListItem.id)
    ).all()
    for item, course in rows:
        if count_reserved(db, item.id) < item.copies_wanted:
            place_copy(db, now, actor_user_id, copy, item, course)
            return True
    return False
