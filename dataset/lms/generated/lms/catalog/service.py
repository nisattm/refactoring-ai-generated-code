"""Business logic of module 4: catalog (LIB-CAT-01 to LIB-CAT-12)."""

from __future__ import annotations

import datetime
from collections.abc import Container
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.service import changes, record
from lms.auth.models import User
from lms.branches.service import require_active_branch
from lms.catalog.models import Author, Book, BookAuthor, Copy, Publisher
from lms.catalog.release import release_copy
from lms.catalog.schemas import (
    MIN_PUBLICATION_YEAR,
    AuthorOut,
    AvailabilityOut,
    BookOut,
    PublisherOut,
)
from lms.catalog.status import GONE_STATUSES, invalid_status, set_status
from lms.core.errors import Conflict, NotFound, ValidationFailed, reference_not_found
from lms.core.text import normalize
from lms.core.timeutil import format_datetime


def _not_found(resource: str, resource_id: int) -> NotFound:
    return NotFound(f"{resource.capitalize()} {resource_id} does not exist", details={"resource": resource, "id": resource_id})


# --- authors and publishers ---------------------------------------------------


def get_author_or_404(db: Session, author_id: int) -> Author:
    author = db.get(Author, author_id)
    if author is None:
        raise _not_found("author", author_id)
    return author


def get_publisher_or_404(db: Session, publisher_id: int) -> Publisher:
    publisher = db.get(Publisher, publisher_id)
    if publisher is None:
        raise _not_found("publisher", publisher_id)
    return publisher


def create_author(db: Session, name: str) -> Author:
    author = Author(name=name, name_key=normalize(name))
    db.add(author)
    db.flush()
    return author


def update_author(author: Author, name: str | None) -> Author:
    if name is not None:
        author.name = name
        author.name_key = normalize(name)
    return author


def delete_author(db: Session, author: Author) -> None:
    if db.scalar(sa.select(BookAuthor.book_id).where(BookAuthor.author_id == author.id).limit(1)) is not None:
        raise Conflict("The author is used by a book", code="IN_USE", details={"id": author.id})
    db.delete(author)


def _check_unique_publisher(db: Session, name: str, *, own_id: int | None = None) -> None:
    stmt = sa.select(Publisher.id).where(Publisher.name_key == normalize(name))
    if own_id is not None:
        stmt = stmt.where(Publisher.id != own_id)
    if db.scalar(stmt) is not None:
        raise Conflict("A publisher with this name already exists", details={"field": "name"})


def create_publisher(db: Session, name: str) -> Publisher:
    _check_unique_publisher(db, name)
    publisher = Publisher(name=name, name_key=normalize(name))
    db.add(publisher)
    db.flush()
    return publisher


def update_publisher(db: Session, publisher: Publisher, name: str | None) -> Publisher:
    if name is not None:
        _check_unique_publisher(db, name, own_id=publisher.id)
        publisher.name = name
        publisher.name_key = normalize(name)
    return publisher


def delete_publisher(db: Session, publisher: Publisher) -> None:
    if db.scalar(sa.select(Book.id).where(Book.publisher_id == publisher.id).limit(1)) is not None:
        raise Conflict("The publisher is used by a book", code="IN_USE", details={"id": publisher.id})
    db.delete(publisher)


# --- books ------------------------------------------------------------------------


def get_book_or_404(db: Session, book_id: int) -> Book:
    book = db.get(Book, book_id)
    if book is None:
        raise _not_found("book", book_id)
    return book


def check_publication_year(year: int, today: datetime.date) -> None:
    """Part of the request validation (422): 1450 to the current year of the clock."""
    if not MIN_PUBLICATION_YEAR <= year <= today.year:
        raise ValidationFailed.single(
            "publication_year", f"publication_year must be between {MIN_PUBLICATION_YEAR} and {today.year}"
        )


def book_author_ids(db: Session, book_id: int) -> list[int]:
    return list(
        db.scalars(sa.select(BookAuthor.author_id).where(BookAuthor.book_id == book_id).order_by(BookAuthor.position))
    )


def _require_authors(db: Session, author_ids: list[int]) -> None:
    for author_id in author_ids:
        if db.get(Author, author_id) is None:
            raise reference_not_found("author_ids", author_id)


def _require_publisher(db: Session, publisher_id: int) -> None:
    if db.get(Publisher, publisher_id) is None:
        raise reference_not_found("publisher_id", publisher_id)


def _check_unique_isbn(db: Session, isbn: str, *, own_id: int | None = None) -> None:
    stmt = sa.select(Book.id).where(Book.isbn == isbn)
    if own_id is not None:
        stmt = stmt.where(Book.id != own_id)
    if db.scalar(stmt) is not None:
        raise Conflict("A book with this ISBN already exists", details={"field": "isbn"})


def _set_authors(db: Session, book: Book, author_ids: list[int]) -> None:
    db.execute(sa.delete(BookAuthor).where(BookAuthor.book_id == book.id))
    db.add_all(BookAuthor(book_id=book.id, author_id=a, position=i) for i, a in enumerate(author_ids))
    db.flush()


def create_book(
    db: Session,
    now: datetime.datetime,
    actor: User,
    *,
    isbn: str,
    title: str,
    subtitle: str | None,
    author_ids: list[int],
    publisher_id: int,
    publication_year: int,
    language: str,
    classification: str,
) -> Book:
    """LIB-CAT-03."""
    _require_authors(db, author_ids)
    _require_publisher(db, publisher_id)
    _check_unique_isbn(db, isbn)
    book = Book(
        isbn=isbn,
        title=title,
        title_key=normalize(title),
        subtitle=subtitle,
        publisher_id=publisher_id,
        publication_year=publication_year,
        language=language,
        classification=classification,
        created_at=now,
    )
    db.add(book)
    db.flush()
    _set_authors(db, book, author_ids)
    record(
        db,
        at=now,
        event="book_created",
        actor_user_id=actor.id,
        entity_type="book",
        entity_id=book.id,
        details={
            "isbn": isbn,
            "title": title,
            "subtitle": subtitle,
            "author_ids": author_ids,
            "publisher_id": publisher_id,
            "publication_year": publication_year,
            "language": language,
            "classification": classification,
        },
    )
    return book


def update_book(db: Session, now: datetime.datetime, actor: User, book: Book, fields: dict[str, Any]) -> Book:
    """LIB-CAT-05. ``fields`` holds only the fields present in the request."""
    if "author_ids" in fields:
        _require_authors(db, fields["author_ids"])
    if "publisher_id" in fields:
        _require_publisher(db, fields["publisher_id"])
    if "isbn" in fields:
        _check_unique_isbn(db, fields["isbn"], own_id=book.id)

    old = {name: book_author_ids(db, book.id) if name == "author_ids" else getattr(book, name) for name in fields}
    diff = changes(old, fields)
    for name, value in fields.items():
        if name == "author_ids":
            if "author_ids" in diff:
                _set_authors(db, book, value)
        else:
            setattr(book, name, value)
    if "title" in fields:
        book.title_key = normalize(book.title)
    if diff:
        record(
            db, at=now, event="book_updated", actor_user_id=actor.id, entity_type="book", entity_id=book.id, details=diff
        )
    return book


def delete_book(db: Session, now: datetime.datetime, actor: User, book: Book) -> None:
    """LIB-CAT-06."""
    if db.scalar(sa.select(Copy.id).where(Copy.book_id == book.id).limit(1)) is not None:
        raise Conflict("The book has copies", code="BOOK_HAS_COPIES", details={"id": book.id})
    details = {"isbn": book.isbn, "title": book.title}
    db.execute(sa.delete(BookAuthor).where(BookAuthor.book_id == book.id))
    db.delete(book)
    db.flush()
    record(db, at=now, event="book_deleted", actor_user_id=actor.id, entity_type="book", entity_id=book.id, details=details)


def is_lendable(db: Session, book_id: int) -> bool:
    """LIB-CAT-12."""
    stmt = sa.select(Copy.id).where(Copy.book_id == book_id, Copy.status.not_in(GONE_STATUSES)).limit(1)
    return db.scalar(stmt) is not None


def availability(db: Session, book_id: int) -> list[AvailabilityOut]:
    """Per current branch: copies ``available`` and copies not ``lost`` or ``withdrawn`` (section 8.1)."""
    rows = db.execute(
        sa.select(
            Copy.current_branch_id,
            sa.func.coalesce(sa.func.sum(sa.case((Copy.status == "available", 1), else_=0)), 0),
            sa.func.coalesce(sa.func.sum(sa.case((Copy.status.in_(GONE_STATUSES), 0), else_=1)), 0),
        )
        .where(Copy.book_id == book_id, Copy.current_branch_id.is_not(None))
        .group_by(Copy.current_branch_id)
        .order_by(Copy.current_branch_id)
    )
    return [AvailabilityOut(branch_id=b, available=int(a), total=int(t)) for b, a, t in rows]


def book_out(db: Session, book: Book) -> BookOut:
    author_rows = db.execute(
        sa.select(Author.id, Author.name)
        .join(BookAuthor, BookAuthor.author_id == Author.id)
        .where(BookAuthor.book_id == book.id)
        .order_by(BookAuthor.position)
    )
    publisher = db.get(Publisher, book.publisher_id)
    assert publisher is not None
    return BookOut(
        id=book.id,
        isbn=book.isbn,
        title=book.title,
        subtitle=book.subtitle,
        authors=[AuthorOut(id=i, name=n) for i, n in author_rows],
        publisher=PublisherOut(id=publisher.id, name=publisher.name),
        publication_year=book.publication_year,
        language=book.language,
        classification=book.classification,
        created_at=format_datetime(book.created_at),
        availability=availability(db, book.id),
    )


# --- copies -----------------------------------------------------------------------


def get_copy_or_404(db: Session, copy_id: int) -> Copy:
    copy = db.get(Copy, copy_id)
    if copy is None:
        raise _not_found("copy", copy_id)
    return copy


def get_copy_by_barcode_or_404(db: Session, barcode: str) -> Copy:
    copy = db.scalar(sa.select(Copy).where(Copy.barcode == barcode.upper()))
    if copy is None:
        raise NotFound(f"No copy has barcode {barcode}", details={"resource": "copy", "barcode": barcode})
    return copy


def check_acquired_on(acquired_on: datetime.date, today: datetime.date) -> None:
    """Part of the request validation (422): not after today."""
    if acquired_on > today:
        raise ValidationFailed.single("acquired_on", "acquired_on must not be after today")


def add_copy(
    db: Session,
    now: datetime.datetime,
    actor: User,
    book: Book,
    *,
    barcode: str,
    home_branch_id: int,
    price: Any,
    acquired_on: datetime.date,
    shelf_location: str | None,
    holidays: Container[datetime.date],
) -> Copy:
    """LIB-CAT-07. Also used for received purchase-order lines (LIB-PUR-06)."""
    require_active_branch(db, "home_branch_id", home_branch_id)
    if db.scalar(sa.select(Copy.id).where(Copy.barcode == barcode)) is not None:
        raise Conflict("A copy with this barcode already exists", details={"field": "barcode"})
    copy = Copy(
        book_id=book.id,
        barcode=barcode,
        home_branch_id=home_branch_id,
        current_branch_id=home_branch_id,
        price=price,
        status="available",
        acquired_on=acquired_on,
        shelf_location=shelf_location,
    )
    db.add(copy)
    db.flush()
    record(
        db,
        at=now,
        event="copy_added",
        actor_user_id=actor.id,
        entity_type="copy",
        entity_id=copy.id,
        details={
            "book_id": book.id,
            "barcode": barcode,
            "home_branch_id": home_branch_id,
            "price": format(price, ".2f"),
            "acquired_on": acquired_on.isoformat(),
            "shelf_location": shelf_location,
        },
    )
    release_copy(db, copy, now, holidays, actor.id)
    return copy


def update_copy(db: Session, now: datetime.datetime, actor: User, copy: Copy, fields: dict[str, Any]) -> Copy:
    """LIB-CAT-09. ``fields`` holds only the fields present in the request."""
    new_home = fields.get("home_branch_id")
    if new_home is not None and new_home != copy.home_branch_id:
        require_active_branch(db, "home_branch_id", new_home)
        if copy.status != "available" or copy.current_branch_id != copy.home_branch_id:
            raise invalid_status(copy, "change of home branch")

    old = {name: getattr(copy, name) for name in fields}
    diff = changes(old, fields)
    for name, value in fields.items():
        setattr(copy, name, value)
    if "home_branch_id" in diff:
        copy.current_branch_id = copy.home_branch_id
    if diff:
        shown = {k: {f: (format(v, ".2f") if k == "price" else v) for f, v in d.items()} for k, d in diff.items()}
        record(
            db, at=now, event="copy_updated", actor_user_id=actor.id, entity_type="copy", entity_id=copy.id, details=shown
        )
    return copy


def withdraw_copy(db: Session, now: datetime.datetime, actor: User, copy: Copy, reason: str) -> Copy:
    """LIB-CAT-10."""
    if copy.status not in ("available", "damaged", "lost"):
        raise invalid_status(copy, "withdrawal")
    set_status(copy, "withdrawn")
    copy.withdrawn_reason = reason
    record(
        db,
        at=now,
        event="copy_withdrawn",
        actor_user_id=actor.id,
        entity_type="copy",
        entity_id=copy.id,
        details={"reason": reason},
    )
    return copy


def repair_copy(
    db: Session, now: datetime.datetime, actor: User, copy: Copy, holidays: Container[datetime.date]
) -> Copy:
    """LIB-CAT-11."""
    if copy.status != "damaged":
        raise invalid_status(copy, "repair")
    record(db, at=now, event="copy_repaired", actor_user_id=actor.id, entity_type="copy", entity_id=copy.id, details={})
    release_copy(db, copy, now, holidays, actor.id)
    return copy
