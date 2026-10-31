"""Export of the JSON dataset and CSV files (LIB-IO-07 to LIB-IO-09, LIB-IO-12 to LIB-IO-14)."""

from __future__ import annotations

import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from lms.audit.exchange_schemas import FORMAT_VERSION
from lms.audit.service import record
from lms.catalog.models import Author, Book, BookAuthor, Copy, Publisher
from lms.branches.models import Branch
from lms.core.money import format_amount
from lms.loans.models import Loan
from lms.members.models import Member
from lms.reports.service import to_csv

CSV_ENTITIES = ("branches", "books", "copies", "members", "loans")

# Columns of the CSV files (section 22.2).
CSV_COLUMNS: dict[str, tuple[str, ...]] = {
    "branches": ("id", "code", "name", "address", "is_active"),
    "books": (
        "id", "isbn", "title", "subtitle", "authors", "publisher", "publication_year", "language", "classification",
    ),
    "copies": (
        "id", "book_id", "barcode", "home_branch_id", "current_branch_id", "price", "status", "acquired_on",
        "shelf_location",
    ),
    "members": (
        "id", "member_no", "full_name", "email", "phone", "membership_type", "university_id", "home_branch_id",
        "status", "membership_start", "valid_until",
    ),
    "loans": (
        "id", "copy_id", "member_id", "branch_id", "loan_date", "due_date", "renewal_count", "status", "returned_on",
        "return_branch_id", "late_days",
    ),
}


def _date(value: datetime.date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _branches(db: Session) -> list[dict[str, Any]]:
    return [
        {"id": b.id, "code": b.code, "name": b.name, "address": b.address, "is_active": b.is_active}
        for b in db.scalars(sa.select(Branch).order_by(Branch.id))
    ]


def _authors(db: Session) -> list[dict[str, Any]]:
    return [{"id": a.id, "name": a.name} for a in db.scalars(sa.select(Author).order_by(Author.id))]


def _publishers(db: Session) -> list[dict[str, Any]]:
    return [{"id": p.id, "name": p.name} for p in db.scalars(sa.select(Publisher).order_by(Publisher.id))]


def _author_ids(db: Session) -> dict[int, list[int]]:
    result: dict[int, list[int]] = {}
    rows = db.execute(
        sa.select(BookAuthor.book_id, BookAuthor.author_id).order_by(BookAuthor.book_id, BookAuthor.position)
    )
    for book_id, author_id in rows:
        result.setdefault(book_id, []).append(author_id)
    return result


def _books(db: Session) -> list[dict[str, Any]]:
    author_ids = _author_ids(db)
    return [
        {
            "id": b.id,
            "isbn": b.isbn,
            "title": b.title,
            "subtitle": b.subtitle,
            "author_ids": author_ids.get(b.id, []),
            "publisher_id": b.publisher_id,
            "publication_year": b.publication_year,
            "language": b.language,
            "classification": b.classification,
        }
        for b in db.scalars(sa.select(Book).order_by(Book.id))
    ]


def _copies(db: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": c.id,
            "book_id": c.book_id,
            "barcode": c.barcode,
            "home_branch_id": c.home_branch_id,
            "current_branch_id": c.current_branch_id,
            "price": format_amount(c.price),
            "status": c.status,
            "acquired_on": _date(c.acquired_on),
            "shelf_location": c.shelf_location,
        }
        for c in db.scalars(sa.select(Copy).order_by(Copy.id))
    ]


def _members(db: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": m.id,
            "full_name": m.full_name,
            "email": m.email,
            "phone": m.phone,
            "membership_type": m.membership_type,
            "university_id": m.university_id,
            "home_branch_id": m.home_branch_id,
            "status": m.status,
            "membership_start": _date(m.membership_start),
            "valid_until": _date(m.valid_until),
        }
        for m in db.scalars(sa.select(Member).order_by(Member.id))
    ]


def _loans(db: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": ln.id,
            "copy_id": ln.copy_id,
            "member_id": ln.member_id,
            "branch_id": ln.branch_id,
            "loan_date": _date(ln.loan_date),
            "due_date": _date(ln.due_date),
            "renewal_count": ln.renewal_count,
            "status": ln.status,
            "returned_on": _date(ln.returned_on),
            "return_branch_id": ln.return_branch_id,
        }
        for ln in db.scalars(sa.select(Loan).order_by(Loan.id))
    ]


def build_document(db: Session) -> dict[str, Any]:
    """The dataset of section 22.1."""
    return {
        "format_version": FORMAT_VERSION,
        "branches": _branches(db),
        "authors": _authors(db),
        "publishers": _publishers(db),
        "books": _books(db),
        "copies": _copies(db),
        "members": _members(db),
        "loans": _loans(db),
    }


def _csv_books(db: Session) -> list[dict[str, Any]]:
    names: dict[int, list[str]] = {}
    rows = db.execute(
        sa.select(BookAuthor.book_id, Author.name)
        .join(Author, Author.id == BookAuthor.author_id)
        .order_by(BookAuthor.book_id, BookAuthor.position)
    )
    for book_id, name in rows:
        names.setdefault(book_id, []).append(name)
    publishers = {p.id: p.name for p in db.scalars(sa.select(Publisher))}
    return [
        {**row, "authors": "; ".join(names.get(row["id"], [])), "publisher": publishers[row["publisher_id"]]}
        for row in _books(db)
    ]


def _csv_members(db: Session) -> list[dict[str, Any]]:
    return [{**row, "member_no": f"M{row['id']:06d}"} for row in _members(db)]


def _csv_loans(db: Session) -> list[dict[str, Any]]:
    late_days = {loan_id: late for loan_id, late in db.execute(sa.select(Loan.id, Loan.late_days))}
    return [{**row, "late_days": late_days[row["id"]]} for row in _loans(db)]


_CSV_ROWS = {
    "branches": _branches,
    "books": _csv_books,
    "copies": _copies,
    "members": _csv_members,
    "loans": _csv_loans,
}


def build_csv(db: Session, entity: str) -> str:
    """CSV text of ``entity`` (one of ``CSV_ENTITIES``), rows ordered by ``id``."""
    return to_csv(CSV_COLUMNS[entity], _CSV_ROWS[entity](db))


def record_export(db: Session, now: datetime.datetime, actor_user_id: int | None, entity: str) -> None:
    """LIB-IO-09."""
    record(
        db,
        at=now,
        event="data_exported",
        actor_user_id=actor_user_id,
        entity_type="dataset",
        entity_id=None,
        details={"entity": entity},
    )
