"""Copies on reserve: placing by hand and taking off reserve (LIB-CRS-19, LIB-CRS-21)."""

from __future__ import annotations

import datetime
from collections.abc import Container

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import record
from lms.auth.models import User
from lms.catalog.models import Copy
from lms.catalog.status import invalid_status
from lms.core.errors import Conflict, NotFound, reference_not_found
from lms.courses import placement
from lms.courses.models import Course, ReadingListItem, ReserveLoan
from lms.courses.schemas import PlacedCopyOut
from lms.reservations.service import release_copy


def _error(code: str, message: str, **details: object) -> Conflict:
    return Conflict(message, code=code, details=details)


def get_item_or_404(db: Session, item_id: int) -> ReadingListItem:
    item = db.get(ReadingListItem, item_id)
    if item is None:
        raise NotFound(f"Reading list item {item_id} does not exist", details={"resource": "reading_list_item", "id": item_id})
    return item


def has_open_loan(db: Session, copy_id: int) -> ReserveLoan | None:
    return db.scalar(sa.select(ReserveLoan).where(ReserveLoan.copy_id == copy_id, ReserveLoan.status == "open"))


def refresh_item_status(db: Session, item: ReadingListItem) -> None:
    """The item is ``requested`` while no copy is on reserve for it (29.1)."""
    if item.status != "removed" and placement.count_reserved(db, item.id) == 0:
        item.status = "requested"


def take_off_reserve(
    db: Session,
    now: datetime.datetime,
    actor_user_id: int | None,
    holidays: Container[datetime.date],
    copy: Copy,
) -> None:
    """The effects of LIB-CRS-21: the copy is released (LIB-RES-08) without being placed on reserve again."""
    item_id, course_id = copy.reserve_item_id, copy.reserve_course_id
    copy.reserve_item_id = None
    copy.reserve_course_id = None
    db.flush()
    item = db.get(ReadingListItem, item_id) if item_id is not None else None
    if item is not None:
        refresh_item_status(db, item)
    record(
        db,
        at=now,
        event="reserve_copy_removed",
        actor_user_id=actor_user_id,
        entity_type="copy",
        entity_id=copy.id,
        details={"item_id": item_id, "course_id": course_id},
    )
    release_copy(db, copy, now, holidays, actor_user_id, course_reserves=False)


def take_all_off_reserve(
    db: Session,
    now: datetime.datetime,
    actor_user_id: int | None,
    holidays: Container[datetime.date],
    *conditions: sa.ColumnElement[bool],
) -> int:
    copies = db.scalars(
        sa.select(Copy).where(Copy.status == "on_reserve", *conditions).order_by(Copy.id)
    ).all()
    for copy in copies:
        take_off_reserve(db, now, actor_user_id, holidays, copy)
    return len(copies)


def unreserve(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date], copy: Copy
) -> Copy:
    """LIB-CRS-21."""
    if copy.status != "on_reserve":
        raise invalid_status(copy, "taking off reserve")
    loan_ids = placement.open_loan_ids(db, ReserveLoan.copy_id == copy.id)
    if loan_ids:
        raise _error("RESERVE_COPY_ON_LOAN", "The copy is on a reserve loan", loan_ids=loan_ids)
    take_off_reserve(db, now, actor.id, holidays, copy)
    return copy


def place_by_hand(
    db: Session, now: datetime.datetime, actor: User, item: ReadingListItem, copy_id: int
) -> PlacedCopyOut:
    """LIB-CRS-19."""
    copy = db.get(Copy, copy_id)
    if copy is None:
        raise reference_not_found("copy_id", copy_id)
    course = db.get(Course, item.course_id)
    assert course is not None
    if course.status == "closed":
        raise _error("INVALID_COURSE_STATUS", "The course is closed", status=course.status)
    if item.status == "removed":
        raise _error("ITEM_REMOVED", "The reading list item was removed", id=item.id)
    if copy.book_id != item.book_id:
        raise _error("WRONG_BOOK", "The copy is of another book", book_id=item.book_id)
    if copy.status != "available":
        raise _error("INVALID_COPY_STATUS", f"Copy {copy.id} has status {copy.status}", id=copy.id, status=copy.status)
    if copy.current_branch_id != course.branch_id:
        raise _error("COPY_AT_OTHER_BRANCH", "The copy is not at the branch of the course", branch_id=course.branch_id)
    if placement.count_reserved(db, item.id) >= item.copies_wanted:
        raise _error("RESERVE_COPIES_COMPLETE", "The item has all the copies it wants", copies_wanted=item.copies_wanted)
    placement.place_copy(db, now, actor.id, copy, item, course)
    return PlacedCopyOut(copy_id=copy.id, barcode=copy.barcode, item_id=item.id, course_id=course.id, on_loan=False)
