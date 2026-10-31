"""Catalog models (section 8.1)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lms.core.db import Base
from lms.core.money import MoneyType
from lms.core.timeutil import TZDateTime


class Author(Base):
    __tablename__ = "authors"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    # Normalized name (LIB-COM-30): the ordering and search key.
    name_key: Mapped[str] = mapped_column(sa.String(200), index=True)


class Publisher(Base):
    __tablename__ = "publishers"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    # Normalized name (LIB-COM-30): the uniqueness, ordering and search key.
    name_key: Mapped[str] = mapped_column(sa.String(200), unique=True)


class Book(Base):
    __tablename__ = "books"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    isbn: Mapped[str] = mapped_column(sa.String(13), unique=True)
    title: Mapped[str] = mapped_column(sa.String(200))
    # Normalized title (LIB-COM-30): the ordering key.
    title_key: Mapped[str] = mapped_column(sa.String(200), index=True)
    subtitle: Mapped[str | None] = mapped_column(sa.String(200), default=None)
    publisher_id: Mapped[int] = mapped_column(sa.ForeignKey("publishers.id"), index=True)
    publication_year: Mapped[int]
    language: Mapped[str] = mapped_column(sa.String(2))
    classification: Mapped[str] = mapped_column(sa.String(10))
    created_at: Mapped[datetime.datetime] = mapped_column(TZDateTime)


class BookAuthor(Base):
    """Authors of a book in the given order (``position`` starts at 0)."""

    __tablename__ = "book_authors"

    book_id: Mapped[int] = mapped_column(sa.ForeignKey("books.id"), primary_key=True)
    author_id: Mapped[int] = mapped_column(sa.ForeignKey("authors.id"), primary_key=True, index=True)
    position: Mapped[int]


class Copy(Base):
    __tablename__ = "copies"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(sa.ForeignKey("books.id"), index=True)
    barcode: Mapped[str] = mapped_column(sa.String(20), unique=True)
    home_branch_id: Mapped[int] = mapped_column(sa.ForeignKey("branches.id"), index=True)
    current_branch_id: Mapped[int | None] = mapped_column(sa.ForeignKey("branches.id"), index=True, default=None)
    price: Mapped[Decimal] = mapped_column(MoneyType)
    status: Mapped[str] = mapped_column(sa.String(20), default="available")
    acquired_on: Mapped[datetime.date] = mapped_column(sa.Date)
    shelf_location: Mapped[str | None] = mapped_column(sa.String(50), default=None)
    withdrawn_reason: Mapped[str | None] = mapped_column(sa.String(500), default=None)
