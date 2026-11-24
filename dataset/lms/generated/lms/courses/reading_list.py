"""Reading lists (LIB-CRS-12 to LIB-CRS-18)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.catalog.models import Book, Copy
from lms.catalog.service import is_lendable
from lms.core.errors import ValidationFailed
from lms.core.errors import conflict as _error
from lms.courses import placement
from lms.courses.courses import count_items
from lms.courses.models import Course, ReadingListItem, ReserveLoan
from lms.courses.reserve import take_all_off_reserve
from lms.courses.rules import MAX_ITEMS
from lms.courses.schemas import ItemOut, item_fields


# --- representation ---------------------------------------------------------------------------


def available_now(db: Session, item_id: int) -> int:
    """Copies on reserve for the item without an open reserve loan."""
    on_loan = sa.select(ReserveLoan.id).where(ReserveLoan.copy_id == Copy.id, ReserveLoan.status == "open")
    stmt = sa.select(sa.func.count()).select_from(Copy).where(
        Copy.reserve_item_id == item_id, Copy.status == "on_reserve", ~on_loan.exists()
    )
    return db.scalar(stmt) or 0


def item_out(db: Session, item: ReadingListItem) -> ItemOut:
    title = db.scalar(sa.select(Book.title).where(Book.id == item.book_id)) or ""
    free = available_now(db, item.id)
    next_due = None
    if free == 0:
        next_due = db.scalar(
            sa.select(sa.func.min(ReserveLoan.due_at)).where(ReserveLoan.item_id == item.id, ReserveLoan.status == "open")
        )
    return item_fields(
        item,
        book_title=title,
        copies_on_reserve=placement.count_reserved(db, item.id),
        available_now=free,
        next_due_at=next_due,
    )


def list_items(db: Session, course_id: int, *, include_removed: bool = False) -> list[ReadingListItem]:
    """LIB-CRS-17."""
    items = list(
        db.scalars(
            sa.select(ReadingListItem)
            .where(ReadingListItem.course_id == course_id, ReadingListItem.status != "removed")
            .order_by(ReadingListItem.position, ReadingListItem.id)
        )
    )
    if include_removed:
        items += list(
            db.scalars(
                sa.select(ReadingListItem)
                .where(ReadingListItem.course_id == course_id, ReadingListItem.status == "removed")
                .order_by(ReadingListItem.id)
            )
        )
    return items


def _details(item: ReadingListItem) -> dict[str, Any]:
    return {
        "kind": item.kind,
        "loan_period": item.loan_period,
        "copies_wanted": item.copies_wanted,
        "note": item.note,
    }


# --- LIB-CRS-12, LIB-CRS-13 ---------------------------------------------------------------------


def add_item(
    db: Session, now: datetime.datetime, actor: User, course: Course, fields: dict[str, Any]
) -> ReadingListItem:
    if course.status == "closed":
        raise _error("INVALID_COURSE_STATUS", "The course is closed", status=course.status)
    book_id = fields["book_id"]
    if db.get(Book, book_id) is None:
        raise ValidationFailed.single("book_id", f"book {book_id} does not exist")
    if not is_lendable(db, book_id):
        raise _error("BOOK_NOT_LENDABLE", "The book has no copy that can be lent", book_id=book_id)
    current = db.scalar(
        sa.select(ReadingListItem.id).where(
            ReadingListItem.course_id == course.id, ReadingListItem.book_id == book_id, ReadingListItem.status != "removed"
        )
    )
    if current is not None:
        raise _error("DUPLICATE_ITEM", "The book is already on the reading list", item_id=current)
    count = count_items(db, course.id)
    if count >= MAX_ITEMS:
        raise _error("READING_LIST_FULL", "The reading list is full", limit=MAX_ITEMS)
    item = ReadingListItem(course_id=course.id, position=count + 1, status="requested", added_at=now, **fields)
    db.add(item)
    db.flush()
    record(
        db,
        at=now,
        event="reading_list_item_added",
        actor_user_id=actor.id,
        entity_type="reading_list_item",
        entity_id=item.id,
        details={"course_id": course.id, "book_id": book_id, "position": item.position, **_details(item)},
    )
    if item.kind == "required":
        placement.place_available_copies(db, now, actor.id, item, course)
    return item


# --- LIB-CRS-14 ---------------------------------------------------------------------------------


def update_item(
    db: Session, now: datetime.datetime, actor: User, item: ReadingListItem, fields: dict[str, Any]
) -> ReadingListItem:
    if item.status == "removed":
        raise _error("ITEM_REMOVED", "The reading list item was removed", id=item.id)
    wanted = fields.get("copies_wanted")
    if wanted is not None:
        reserved = placement.count_reserved(db, item.id)
        if wanted < reserved:
            raise _error(
                "COPIES_WANTED_BELOW_RESERVE", "copies_wanted is below the copies on reserve", on_reserve=reserved
            )
    old = _details(item)
    for name, value in fields.items():
        setattr(item, name, value)
    record(
        db,
        at=now,
        event="reading_list_item_updated",
        actor_user_id=actor.id,
        entity_type="reading_list_item",
        entity_id=item.id,
        details=changes(old, _details(item)),
    )
    return item


# --- LIB-CRS-15 ---------------------------------------------------------------------------------


def order_items(db: Session, actor_course: Course, item_ids: list[int]) -> list[ReadingListItem]:
    items = list_items(db, actor_course.id)
    if sorted(item_ids) != sorted(i.id for i in items) or len(set(item_ids)) != len(item_ids):
        raise ValidationFailed.single(
            "item_ids", "item_ids must contain every item of the course that is not removed exactly once"
        )
    by_id = {i.id: i for i in items}
    for position, item_id in enumerate(item_ids, start=1):
        by_id[item_id].position = position
    db.flush()
    return [by_id[i] for i in item_ids]


# --- LIB-CRS-16 ---------------------------------------------------------------------------------


def remove_item(
    db: Session, now: datetime.datetime, actor: User, holidays: Container[datetime.date], item: ReadingListItem
) -> ReadingListItem:
    if item.status == "removed":
        raise _error("ITEM_REMOVED", "The reading list item was removed", id=item.id)
    loan_ids = placement.open_loan_ids(db, ReserveLoan.item_id == item.id)
    if loan_ids:
        raise _error("RESERVE_COPY_ON_LOAN", "A copy of the item is on a reserve loan", loan_ids=loan_ids)
    take_all_off_reserve(db, now, actor.id, holidays, Copy.reserve_item_id == item.id)
    old_position = item.position
    item.status = "removed"
    item.position = None
    db.flush()
    if old_position is not None:
        later = db.scalars(
            sa.select(ReadingListItem).where(
                ReadingListItem.course_id == item.course_id,
                ReadingListItem.status != "removed",
                ReadingListItem.position > old_position,
            )
        ).all()
        for other in later:
            assert other.position is not None
            other.position -= 1
    record(
        db,
        at=now,
        event="reading_list_item_removed",
        actor_user_id=actor.id,
        entity_type="reading_list_item",
        entity_id=item.id,
        details={"course_id": item.course_id, "book_id": item.book_id},
    )
    return item
